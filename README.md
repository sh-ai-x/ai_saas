# AI SaaS foundation

This is the smallest runnable, contract-first foundation extracted from the
`mysaas` baseline. It keeps the first deployment as a modular monolith while
recording logical ownership and versioned REST, SSE, event, and provider
boundaries for service extraction.

It contains no provider SDK, cloud provisioning, or secret. Provider-neutral
billing uses application-owned capability ports, signed webhook adapters, and
SQLite/PostgreSQL-compatible transactional persistence; provider SDKs are not
part of the domain. Local Docker uses PostgreSQL 17 only as a development
companion; the HTTP surface itself is Python standard library code.

## Toolchain

JavaScript dependencies are managed from the repository root with `pnpm` and
the committed `pnpm-lock.yaml`; do not use `npm install`, `npm ci`, or `npx`.
The web workspace is selected with `pnpm --filter ai-saas-foundation-web ...`.
Python dependencies and commands run through the committed `uv.lock`; use
`uv sync --locked` and `uv run --locked ...` rather than mutating the host
Python installation with `pip`.

The cloud database baseline is Neon PostgreSQL. The linked project is
`ai_saas` (`lucky-boat-01406333`) on the `production` branch. Local Docker and
the process-only profile remain disposable development paths; they do not
commit or replace the Neon credentials.

See [docs/neon-database.md](docs/neon-database.md) for the repeatable Neon
setup, environment-variable flow, policy deployment, and connection check.

## Start locally

The safest quick path is a generated process-only secret that is never written
to Git:

```bash
export APP_SECRET_KEY="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --locked python -m foundation.config \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
uv run --locked python -m lib.intent_integrity --pre ai-saas-foundation
uv run --locked python -m foundation.server \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
```

In another terminal, check `http://127.0.0.1:8080/healthz`,
`/v1/contracts`, or `/v1/runs/demo/events`. The server validates all required
settings before binding a port and never prints secret values.

### Web console

The local browser console lives in `apps/web` and talks to the same API through
a same-origin Next.js proxy. Start the API first, then run:

```bash
pnpm install
pnpm --filter ai-saas-foundation-web dev
```

Open `http://localhost:3000` for the product landing and operator console. The
separate setup guide is at `http://localhost:3000/guides`. The default local
profile provides the product console, bounded runs with SSE replay, audited
admin plan/credit changes, and the provider-neutral mock payment adapter. Live
Google login is intentionally not mocked; `/login` shows the setup notice until
the staging environment below is configured.

For a production-style local check, use `pnpm --filter ai-saas-foundation-web build`
and then `pnpm --filter ai-saas-foundation-web start` from the repository root.

The local server includes a complete deterministic vertical slice:

```bash
# mock Google OAuth start/callback
curl http://127.0.0.1:8080/v1/auth/google/start

# synchronous local run; the response is also persisted for SSE replay
curl -X POST http://127.0.0.1:8080/v1/runs \
  -H 'content-type: application/json' \
  -d '{"contract_version":"v1","tenant_id":"demo-tenant","project_id":"demo-project","idempotency_key":"run-local-001","trace_id":"trace-local-001","input":{"message":"hello"}}'

# inspect the run's replayable events after replacing RUN_ID
curl http://127.0.0.1:8080/v1/runs/RUN_ID/events

# create and complete a mock payment through the same signed webhook path
curl -X POST http://127.0.0.1:8080/v1/billing/orders \
  -H 'content-type: application/json' \
  -d '{"order_id":"order-local-001","idempotency_key":"order-key-local-001","credit_grant":10}'
curl -X POST http://127.0.0.1:8080/v1/billing/mock/complete \
  -H 'content-type: application/json' \
  -d '{"order_id":"order-local-001"}'

# tenant-scoped admin mutation; the credit change uses the same local ledger
curl -X POST http://127.0.0.1:8080/v1/admin/credits \
  -H 'content-type: application/json' \
  -d '{"target_user_id":"demo-user","amount":3,"reason":"local demo"}'
```

`uv run --locked python scripts/local-smoke.py` runs this flow automatically. It succeeds on
a host without Docker; if Docker Desktop is stopped it records
`docker=blocked (daemon unavailable)` and does not suggest a paid upgrade.

## Real integration setup guides

The provider-ready path is documented in [docs/setup-guides/README.md](docs/setup-guides/README.md)
and rendered on the dedicated `/guides` route as a Markdown editor with a
hierarchical sidebar. Payment setup is split into `Toss` and `Lemon Squeezy`
pages. The order is intentional: contracts and validators first, then Google
OAuth, one payment sandbox, one Agent provider, and finally the full
verification gate. No secret is required for the default local profile.

### Live Google OAuth + Neon setup

Use this path when you want a real Google login against the Neon database. The
default local profile remains credential-free. Run all commands from the
repository root.

#### 1. Install and authenticate the Neon CLI

```bash
pnpm install
pnpm add --global neon@latest
neon auth
```

Complete the Neon login in the normal browser profile. The setup script uses
the current repository project (`lucky-boat-01406333`) and `production` branch
by default. To use another project, pass `--neon-project-id` and
`--neon-branch` in the final command.

#### 2. Save the Google client values once

Create `apps/web/.env.local` from the example only if it does not exist, then
add the server-side Google values obtained from Google Cloud:

```bash
test -f apps/web/.env.local || cp apps/web/.env.example apps/web/.env.local
```

```dotenv
GOOGLE_CLIENT_ID=your-web-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-server-only-client-secret
```

Register this exact callback in Google Cloud:
`http://localhost:3000/api/auth/callback/google`. Do not use `127.0.0.1`, add
a trailing slash, or expose `GOOGLE_CLIENT_SECRET` through a `NEXT_PUBLIC_*`
variable.

#### 3. Link Neon, configure Better Auth, and migrate Drizzle tables

```bash
pnpm web:setup-auth -- --link-neon --migrate
```

The command performs the remaining setup in order:

1. links the Neon `production` branch and receives the ignored root `.env.local`;
2. copies the pooled `DATABASE_URL` into `apps/web/.env.local`;
3. copies `DATABASE_URL_UNPOOLED` when Neon provides it;
4. reuses `BETTER_AUTH_SECRET` or generates a new server-only secret;
5. sets `APP_ENV=staging`, `BETTER_AUTH_URL`, and the Google-enabled flag;
6. runs `pnpm --filter ai-saas-foundation-web db:migrate` through Drizzle.

The migration creates or updates the Better Auth identity tables (`app_user`,
`account`, `session`, `verification`) and the pricing/payment/admin tables.
The script is idempotent for an already-linked branch, preserves unrelated
environment variables, writes `.env.local` with restrictive permissions, and
never prints secret values. To configure without changing the database, omit
`--migrate`; to use an already-linked branch, omit `--link-neon`.

#### 4. Start and verify the live login

```bash
pnpm web:dev
```

Open [http://localhost:3000/login](http://localhost:3000/login) and select
**Continue with Google**. After the callback, verify that the browser returns
to `/app`, the session control shows the Google account, and `/admin` is
available only when that account's persisted `app_user.role` is `admin` or
`super_admin`.

For a read-only table check, load the app environment in the current shell and
query only table names:

```bash
set -a
source apps/web/.env.local
set +a
psql "$DATABASE_URL" -c \
  "select tablename from pg_tables where schemaname = 'public' and tablename in ('app_user','account','session','verification') order by tablename;"
```

#### Setup troubleshooting

| Symptom | Resolution |
|---|---|
| `web:setup-auth` is not found | Pull the merged `main` branch and run `pnpm install` from the repository root. |
| `DATABASE_URL` is missing | Run the command with `--link-neon`, confirm Neon CLI authentication, and check the linked branch. |
| `GOOGLE_CLIENT_ID` or secret is missing | Keep both values in `apps/web/.env.local`; the script fails before rewriting the file when either is absent. |
| `redirect_uri_mismatch` | Use `http://localhost:3000/api/auth/callback/google` exactly in Google Cloud and `BETTER_AUTH_URL`. |
| Drizzle reports schema/relation already exists notices | These are idempotent PostgreSQL notices; confirm the final `migrations applied successfully` message. |
| `auth_not_configured` remains after setup | Stop and restart `pnpm web:dev`; Next.js reads environment variables when the server starts. |

Never commit either `.env.local` file, Neon credentials, Google secrets, or the
Better Auth secret. The full category-based guides are also rendered at
`/guides`.

### Drizzle database workflow

Drizzle is the schema and migration source of truth for the web database:

- schema: `apps/web/db/schema/`
- migration output: `apps/web/drizzle/`
- configuration: `apps/web/drizzle.config.ts`
- migration history: `neondb.drizzle.__drizzle_migrations`

After changing a schema file, generate and review a migration before applying
it:

```bash
pnpm web:db:generate
git diff -- apps/web/drizzle
```

Apply the committed migration to the intended environment with the unpooled
connection string. Drizzle prefers `DATABASE_URL_UNPOOLED` and falls back to
`DATABASE_URL` for local PostgreSQL; it never selects a Neon branch implicitly:

```bash
# local Docker: web-migrate runs this automatically during docker:local
pnpm docker:local

# an explicitly selected Neon preview or staging branch
DATABASE_URL_UNPOOLED="$DATABASE_URL_UNPOOLED" pnpm web:db:migrate
```

For a Neon preview branch, create or select the branch with Neon MCP/CLI first,
then load its ignored connection variables before running the migration. Never
use the production connection string from a developer worktree. The normal
cloud sequence is: create branch from `staging` → run Drizzle migration → run
verification checks → delete the preview branch when the worktree or PR is
retired.

`pnpm docker:local` intentionally forces the web migration and application to
the worktree-local PostgreSQL database, even if `.env` contains a Neon URL.
For an explicit remote-preview diagnostic only, opt in for that invocation:

```bash
ALLOW_REMOTE_DATABASE=true \
WEB_DATABASE_URL="$DATABASE_URL" \
WEB_DATABASE_URL_UNPOOLED="$DATABASE_URL_UNPOOLED" \
pnpm docker:local
```

Review the target branch and migration output before using this escape hatch;
the web process uses the pooled `WEB_DATABASE_URL`, while the Docker
`web-migrate` service uses the direct `WEB_DATABASE_URL_UNPOOLED`.

### Docker runtime with Neon

Use the Neon Compose profile when the web console must run against a Neon
preview or staging branch. It does not start a local PostgreSQL container:

```bash
cp .env.neon.example .env.neon
# Fill DATABASE_URL with the pooled URL and DATABASE_URL_UNPOOLED with the
# direct URL from the selected Neon branch, then add the runtime secrets.
pnpm docker:neon
```

`docker:neon` derives an isolated `3200`/`8280` host-port block per worktree.
The web container receives the pooled `DATABASE_URL`; the one-shot
`web-migrate` container receives only `DATABASE_URL_UNPOOLED`. Stop that
worktree with `pnpm docker:neon:down`. Create/select the Neon branch with Neon
MCP or the Neon CLI before copying its URLs; the Docker command never creates,
deletes, or promotes a Neon branch.

## Docker path

Docker Compose starts the local PostgreSQL companion and the same HTTP surface.
No cloud account, ALB, NAT gateway, Redis, or paid plan is needed.

```bash
cp config/profiles/free-portfolio.example.env .env
export APP_SECRET_KEY="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose -f docker/dev/compose.yaml up --build
```

Stop and remove the local database volume with `docker compose -f
docker/dev/compose.yaml down -v` when its disposable development data is no
longer needed.

## Full Docker web deployment

The complete local stack is also containerized: PostgreSQL, the Foundation API,
a one-shot Drizzle migration job, and the Next.js web console. The local web
override uses Next.js development mode to avoid the expensive standalone trace
build on an 8 GB laptop; release-shaped images still use standalone output.
The browser calls the API through the internal `foundation:8080` service name.
Each Git worktree receives a separate Compose project, host-port block, and
PostgreSQL volume. See [ADR-0002](docs/adr/0002-worktree-port-and-database-isolation.md)
for the local/preview/staging/production database boundary.

```bash
cp .env.docker.example .env
pnpm docker:local
```

The first available slot uses `http://localhost:3100` for the web console and
`http://localhost:8180/healthz` for the API health check. Other worktrees get
the next free block (`+10` per slot), and the Compose output prints the exact
published ports. The Docker-only host ports are intentionally separate from
the process-mode/legacy defaults (`3000`, `8080`, and `5432`). Container-to-
container URLs remain `web:3000`, `foundation:8080`, and `postgres:5432`.
The default profile uses mock payments, while the browser has no local/mock
login fallback. Local Compose PostgreSQL uses trust authentication and does
not require `POSTGRES_PASSWORD`. For live Google login, fill
`BETTER_AUTH_SECRET`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` in the
ignored root `.env`; `docker:local` forces `WEB_DATABASE_URL` to the local
Compose PostgreSQL unless `ALLOW_REMOTE_DATABASE=true` is explicitly set.
Register the actual published web port shown by Compose for the Google
callback.

`pnpm docker:local` always reads the root `.env`, rebuilds the images, and
force-recreates the containers. This is important after changing Google OAuth
or database settings because an existing container keeps its old environment.
If `APP_SECRET_KEY` is blank, the script generates an ephemeral value for that
run; set a persistent value in `.env` when session continuity across restarts
matters. The script can be run from any directory inside this repository.

The `web-migrate` service must complete before `web` starts. This is suitable
for a single-host portfolio or staging deployment. For multiple web replicas,
run migrations as a separate release job rather than once per replica.

```bash
pnpm docker:local down
pnpm docker:local down --volumes  # also removes this worktree's local data
```

The production Compose file is a packaging baseline, not a managed high
availability platform. Put TLS/WAF at the host or edge, use Neon instead of
the bundled PostgreSQL service for production data, and move secrets to the
host's secret manager.

## Profile checks

`free-portfolio` requires the mock provider, local workflow mode, a generated
secret, and worker disabled. `aws-worker` additionally requires explicit
non-secret worker identifiers and the fixed low-cost boundary: Fargate Spot,
ARM64, 0.25 vCPU, 512 MiB, public-subnet outbound access, and no inbound rules.
Both profiles reject missing settings and paid/always-on ALB, NAT, Redis, or
plan configuration. The AWS example is intentionally incomplete and should
fail until an operator supplies its identifiers:

```bash
uv run --locked python -m foundation.config \
  --env-file config/profiles/aws-worker.example.env \
  --profile aws-worker
```

Each profile has explicit per-tenant run/unit counters. A limit creates a
durable `quota_paused` run before credit reservation or worker dispatch; it
never upgrades the request to paid capacity. Sampled telemetry defaults to a
bounded in-memory exporter and redacts prompts, payment data, OAuth codes,
credentials, authorization headers, and tokens.

Run the deterministic contract suite at any time:

```bash
uv run --locked python -m foundation.contract_check
uv run --locked python -m unittest discover -s tests -v
```

Run the web HTTP E2E suite with a disposable `APP_ENV=test` Next.js server:

```bash
pnpm web:e2e
```

This covers the public/login pages, Google OAuth fail-closed behavior, the
test-only signup/login/logout fixture, session revocation, member versus admin
authorization, admin subscription catalog creation and one-time/subscription
policy switching, invalid checkout responses, Toss and Lemon Squeezy sandbox
handoffs, and a JSON 503 response when the Foundation API is unavailable. The
fixture never exists outside `APP_ENV=test`, and the payment assertions only
use test credentials and never grant a live entitlement.

The complete local gate, including evaluator evidence and Docker Compose
configuration validation, is `scripts/verify-local.sh`. It does not require a
cloud account; if Docker is unavailable it reports the Compose check as
skipped.

Step evidence is compact, valid JSON rather than a raw agent transcript:

```bash
uv run --locked python scripts/record-step-outputs.py --all
```

This writes `phases/ai-saas-foundation/step0-output.json` through
`step12-output.json` with the real command exit code, stdout, stderr, and
duration. Docker availability and browser-console verification are preserved
as explicit environment notes.

See [docs/service-catalog.md](docs/service-catalog.md) for ownership and
[`packages/contracts/`](packages/contracts/) for the v1 wire contracts.

## Billing boundary

`services/billing/` owns pending orders, the provider inbox, normalized event
processing, entitlements, credits, and audit records. `MockPaymentAdapter` is
test-only; `TossPaymentsAdapter` and `LemonSqueezyAdapter` verify raw webhook
requests and normalize provider statuses before the shared transaction applies
effects. Select exactly one provider with `PAYMENT_PROVIDER`; production
rejects the mock provider. Access is granted only from a verified, persisted
provider event, never from a client success redirect. The web E2E suite checks
provider-neutral checkout context and secret redaction; the Python suite checks
Toss confirmation idempotency, amount matching, webhook signatures, and Lemon
Squeezy JSON:API/webhook normalization.

## Identity and privileged operations

`services/identity_tenant/` is the server-side identity boundary. It accepts
Better Auth-compatible server session results, validates Google callback state,
issuer, exact redirect URI, one-time use, and verified provider subject, then
derives tenant membership and RBAC from stored records. Browser-provided role
or email fields are never authorization inputs.

`services/admin_operations/` exposes user inspection, plan transition, and
credit adjustment use cases. Mutations require an authorized tenant-scoped
operator and a reason, call entitlement/ledger ports, and append immutable
before/after audit evidence. Cross-tenant requests fail before a domain port is
called. The local composition root maps admin credit changes to the same
SQLite account used by run reservations and mock payment grants, so the demo
does not display a balance that differs from the executable balance.

## Durable agent runs

`services/run_service` owns idempotent run creation, explicit queued/running/
approval/completed/failed/cancelled transitions, SQLite-backed checkpoints, and
replayable SSE frames. `services/metering_billing.SQLiteCreditLedger` reserves
credits before a workflow event is published and commits or releases them with
stable idempotency keys.

`services/agent_worker.BoundedWorker` bounds steps, model calls, and wall-clock
time, checkpoints the model-call key before invocation, and resumes safely
after interruption. `InngestDispatcher` carries only run identifiers and
limits; `FargateSpotBoundary` is an optional ARM64 worker-only launch
description with no inbound route. Prompts and payment payloads are excluded
from workflow/SSE payloads and redacted from streamed output.
