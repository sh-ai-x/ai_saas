---
id: database-neon
category: DATABASE
title: Neon PostgreSQL
summary: Select a Neon environment, inject connection variables safely, and verify the database without exposing credentials.
---

# Neon PostgreSQL

Neon is the cloud database baseline for the foundation. Local Docker remains
the disposable development path; named Neon `stage2` and `production` branches
are durable cloud environments. See the [deployment runbook](../sot/operations/deployment-runbook.md)
for the complete branch, migration, Vercel, and rollback contract.

## 1. Authenticate from a supported browser

Run the CLI from a normal local terminal and finish the OAuth flow in the
existing Chrome or Safari profile. Do not use an embedded browser or commit a
token.

```bash
pnpm add --global neon@latest
neon auth
```

## 2. Install project tooling

Install the Neon agent skills and MCP configuration only on a trusted
developer machine. The MCP command creates an account-scoped credential in
local agent configuration; rotate or revoke it if the machine is shared.

```bash
neon skills -y
neon mcp -y
```

## 3. Link the production branch

The current project is `ai_saas` (`lucky-boat-01406333`). Replace the project
ID when setting up a derivative project.

```bash
neon link --project-id lucky-boat-01406333 --branch production -y
```

This creates the ignored `.neon` context and pulls `DATABASE_URL`,
`DATABASE_URL_UNPOOLED`, and `NEON_BRANCH` into the ignored `.env.local` file.

For the web app, run the setup command after linking. It copies the Neon URL
into `apps/web/.env.local`, generates the Better Auth secret if needed, and
validates Google OAuth values. It does not apply a cloud migration:

```bash
pnpm web:setup-auth -- --neon-branch stage2 --app-env staging
```

Add `--link-neon` when the branch has not been linked yet.
Run the staging `verify → plan → apply → verify` gate below for database
changes; do not call the web package's raw migration command against Neon.

The Drizzle configuration uses `DATABASE_URL_UNPOOLED` for migrations and
`DATABASE_URL` for application traffic. This is intentional: keep the direct
Neon connection for schema changes and the pooled connection for runtime
queries. To run the web console in Docker against the selected branch, use
the Neon-specific profile instead of the local PostgreSQL profile:

```bash
cp .env.neon.example .env.neon
# Copy DATABASE_URL and DATABASE_URL_UNPOOLED from the selected branch into
# .env.neon, then add the required application and OAuth secrets.
pnpm docker:neon
```

The local profile remains:

```bash
pnpm docker:local
```

It starts a separate PostgreSQL volume for the current Git worktree and does
not silently use a Neon URL.

## 4. Apply the repository policy

The committed `neon.ts` deliberately starts with an empty policy so existing
Neon project defaults are preserved. Preview first, then apply.

```bash
neon config init
neon config plan
neon deploy
```

## 5. Verify the connection

Run a read-only query against the linked branch.

```bash
neon status --output json
neon psql production -- -c "select current_database(), current_schema(), current_setting('server_version');"
```

Expected output includes database `neondb`, schema `public`, and a current
Neon PostgreSQL version. Never print or paste the full connection string.

## 6. Select the deployment mode

The local `free-portfolio` profile intentionally uses disposable local
storage so a fresh clone can run without cloud credentials. Cloud deployment
injects the ignored Neon variables through the host secret manager. Neon
provisioning does not enable payment or model-provider secrets and does not
replace the integration validators.

## 7. Verify and migrate the staging branch

For the shared staging branch, keep `DATABASE_URL` pooled for application
traffic and use `DATABASE_URL_UNPOOLED` for Drizzle migrations. The preflight
must pass before the apply command is allowed to continue:

```bash
NEON_BRANCH=stage2 \
pnpm run db:verify:stage -- --from-file "$PWD/.env.stage"

NEON_BRANCH=stage2 \
pnpm run db:plan:stage -- --from-file "$PWD/.env.stage"

CONFIRM_STAGING_DB=staging \
NEON_BRANCH=stage2 \
pnpm run db:migrate:stage -- --from-file "$PWD/.env.stage"
```

Success requires `migration-history: current`, no pending migrations, and the
final `migration release: APPLY PASS` message. PostgreSQL notices about an
existing `drizzle` schema or migration table are harmless idempotency notices.

If preflight reports `migration-history: incompatible`, stop the release and
open a reviewed repair change. Never edit or delete
`drizzle.__drizzle_migrations` manually, and never use a developer worktree to
repair production history.
