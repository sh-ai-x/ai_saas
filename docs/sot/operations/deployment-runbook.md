---
doc_id: operations-deployment-runbook
domain: operations
purpose: Define the low-cost Git, Neon, Docker, Vercel, EC2, migration, and rollback release contract.
read_when:
  - changing branches, environments, deployments, migrations, Docker ports, or rollback
  - preparing a staging release or production-shaped portfolio deployment
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../architecture/system-map.md
  - ../security/safety-boundaries.md
  - ../verification/release-and-incident.md
source_of_truth: contract
owner: platform-engineering
last_reviewed: 2026-09-23
change_impact: high
---

# Deployment and branch runbook

This is the operational source of truth for the low-cost portfolio/staging
deployment. The current product is a modular monolith: Next.js on Vercel is
the preferred public runtime, Neon PostgreSQL is the cloud database, and
Docker is the reproducible local or single-host fallback. Real payments are
not enabled for the portfolio deployment.

## 1. Environment boundaries

| Environment | Application runtime | Database | Purpose |
|---|---|---|---|
| local | `pnpm docker:local` | worktree-local PostgreSQL | disposable development |
| preview | Vercel Preview or `pnpm docker:neon` | disposable Neon branch | PR validation |
| staging | Vercel Preview/alias or local verification | shared Neon `stage2` branch | user feedback and release candidate |
| production-shaped | Vercel Production deployment | protected Neon `production` branch | portfolio demonstration only; no live payment |

The Git branch and Neon branch are different objects. A Git PR branch may use
a disposable Neon branch for isolation; the shared staging database is always
selected explicitly with `NEON_BRANCH=stage2`. Never infer a database target
from the current Git branch name.

## 2. Git branch policy

- `main` is protected. All changes enter through a PR with passing checks.
- Use `feat/*` for product work, `fix/*` for defects, and `docs/*` for
  documentation-only changes.
- A PR branch deploys to Vercel Preview. Preview builds do not migrate the
  shared staging or production database.
- Merge to `main` only after local tests, database preflight, and the Vercel
  preview smoke check pass.
- A `hotfix/*` branch starts from `main`, is verified against staging first,
  and uses the same production approval gate. After merge, sync `main` back to
  any long-lived development branch; do not develop further on the hotfix.
- Use squash merge for one logical change. Do not commit secrets, `.env*`
  files, Neon URLs, OAuth secrets, or payment keys.

## 3. Local Docker workflow

The local command deliberately forces the web runtime and Drizzle migration to
the worktree-local PostgreSQL service, even if a Neon URL is present in `.env.local`:

```bash
cp .env.local.example .env.local
pnpm docker:local
```

The stable internal ports are web `3000`, Foundation `8080`, and PostgreSQL
`5432`. Host ports are fixed per profile:

| Profile | Web | Foundation | PostgreSQL |
|---|---:|---:|---:|
| `pnpm --filter ai-saas-foundation-web dev` (process-only) | `3000` | `8080` | `5432` |
| `pnpm docker:local` | `3100` | `8180` | `55433` |
| `pnpm docker:neon` | `3200` | `8280` | — |

Stop one worktree with `pnpm docker:local down`; add `--volumes` only when
its local data is disposable.

To run the web console against a selected Neon branch instead of local
PostgreSQL:

```bash
cp .env.staging.example .env.staging
pnpm docker:neon
```

The Neon profile does not start PostgreSQL. It uses the pooled URL for runtime
traffic, the direct URL for the one-shot migration container, and exposes the
web console on host port `3200` and the API on `8280`.

## 4. Drizzle and Neon migration workflow

`apps/web/db/schema/` and the committed files in `apps/web/drizzle/` are the
source of truth. Use this sequence for a schema change:

```bash
pnpm run web:db:generate
git diff -- apps/web/drizzle
```

For the shared staging branch, `.env.staging` must contain `APP_ENV=staging`,
the pooled `DATABASE_URL`, and the direct `DATABASE_URL_UNPOOLED`. Supply the
branch name explicitly:

```bash
NEON_BRANCH=stage2 \
pnpm run db:verify:stage -- --from-file "$PWD/.env.staging"

NEON_BRANCH=stage2 \
pnpm run db:plan:stage -- --from-file "$PWD/.env.staging"

CONFIRM_STAGING_DB=staging \
NEON_BRANCH=stage2 \
pnpm run db:migrate:stage -- --from-file "$PWD/.env.staging"
```

The order is mandatory:

1. `db:verify:stage` performs a read-only environment, TLS, direct-connection,
   destructive-SQL, database identity, pgvector, and migration-history check.
2. `db:plan:stage` repeats the preflight and makes no database changes.
3. `db:migrate:stage` requires explicit staging confirmation, runs Drizzle once
   on the direct connection, and verifies history after the migration.

The expected success conditions are `migration-history: current`, no pending
migrations, no unexpected rows, and `migration release: APPLY PASS`. PostgreSQL
notices that the `drizzle` schema or `__drizzle_migrations` table already
exists are normal idempotency notices.

If history is `incompatible`, stop. Do not retry the apply command, edit the
history table manually, or create a new migration that hides the divergence.
Open a reviewed staging repair change with an explicit data-preservation plan.

Production is CI-only:

```bash
CONFIRM_PRODUCTION_PREFLIGHT=production \
pnpm run db:plan:prod -- --from-file "$PWD/.env.production"
```

`db:migrate:prod` additionally requires `CONFIRM_PRODUCTION_DB=production`
and `GITHUB_ACTIONS=true`. A production migration must be a separate approved
release step, never a Vercel build hook or developer-shell command.

## 5. Vercel deployment strategy

Configure the Vercel project with Git integration using this mapping:

| Event | Vercel target | Environment variables |
|---|---|---|
| PR branch | Preview | preview URL, staging-safe OAuth, staging Neon only when explicitly needed |
| merge to `main` | Production | production URL and production-scoped secrets |
| branch push without PR | Preview only | no production secrets |

The Vercel build command builds the application; it does not run database
migrations. The release sequence is:

```text
PR checks -> Vercel Preview -> application smoke test
          -> staging preflight/plan/apply/verify
          -> merge main -> Vercel Production deployment
```

For a deployed Preview or Production URL, perform a read-only smoke check
before accepting the deployment:

```bash
curl -fsS "$VERCEL_PREVIEW_URL/login" >/dev/null
curl -fsS "$VERCEL_PREVIEW_URL/api/pricing" >/dev/null
```

The URL variable is supplied by the operator or Vercel deployment output; do
not commit it as configuration. These checks validate that the app responds
without creating a user, order, payment, or migration.

For this portfolio, keep `PAYMENT_PROVIDER=mock` or sandbox-only settings and
do not attach live payment credentials. Google OAuth may use a staging/test
client. Vercel environment variables must be configured separately for
Preview, Production, and any local `.env` file; never copy a production Neon
URL into a Preview environment.

Rollback at Vercel is an application deployment rollback to the previous
known-good deployment. It does not roll back database state. Database changes
are forward-only: use an additive corrective migration, or restore a managed
Neon backup/branch after an approved incident decision.

## 6. EC2 fallback

EC2 is an optional single-host alternative when a Docker runtime is required.
Use one small instance, Docker Compose, a security group exposing only HTTPS,
and a reverse proxy such as Caddy or Nginx. Keep Neon as the database; do not
run a second production PostgreSQL unless there is a deliberate backup and
restore plan.

The EC2 release sequence is:

```text
build immutable image -> copy/pull image -> health-check image
-> run direct Neon migration once -> start new web container
-> health-check -> switch reverse proxy -> retain previous image for rollback
```

Do not run migrations in every replica or container startup. For this project,
Vercel is the lower-operations-cost default; EC2 is useful only when long-lived
Docker processes, custom networking, or a background worker justify the host
cost and maintenance.

## 7. Hotfix and rollback rules

- Application rollback: redeploy the previous Vercel deployment or previous
  immutable EC2 image.
- Database rollback: never delete or rewrite Drizzle history as a rollback.
  Ship a reviewed forward migration, or restore a Neon backup/branch when the
  incident requires data restoration.
- Hotfix: branch from `main`, reproduce against staging, run the normal
  preflight and migration plan, merge the PR, then promote the application.
- If a migration is destructive, the preflight must fail until a reviewer
  explicitly enables and documents the operation. Prefer additive changes and
  expand/contract migrations.

## 8. Cost and scope boundary

The recommended portfolio topology is Vercel + Neon + local Docker. It avoids
always-on EC2, ALB, NAT Gateway, Redis, and a second managed database. Add EC2
only for a demonstrated runtime requirement, and add production payment or
worker infrastructure only after real user feedback justifies the cost.
