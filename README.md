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

Open `http://127.0.0.1:3000` for the product landing and operator console. The
separate setup guide is at `http://127.0.0.1:3000/guides`. The console demonstrates mock Google login, a
bounded run with SSE replay, audited admin plan/credit changes, and the
provider-neutral mock payment adapter. It does not require Vercel, Neon,
Cloudflare, AWS, Docker, or payment credentials.

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
a one-shot Drizzle migration job, and the Next.js web console. The web image
uses Next.js standalone output and calls the API through the internal
`foundation:8080` service name.

```bash
cp .env.docker.example .env
export APP_SECRET_KEY="$(openssl rand -base64 32)"
docker compose -f docker/prod/compose.yaml up --build
```

Open `http://localhost:3000` for the web console and
`http://localhost:8080/healthz` for the API health check. The default profile
uses mock payments, while the browser has no local/mock login fallback. Set
`WEB_DATABASE_URL` to the Neon connection string and provide the live
Google OAuth/payment secrets through the ignored `.env` file when running a
staging-like container. The Google callback for this local container remains:
`http://localhost:3000/api/auth/callback/google`.

The `web-migrate` service must complete before `web` starts. This is suitable
for a single-host portfolio or staging deployment. For multiple web replicas,
run migrations as a separate release job rather than once per replica.

```bash
docker compose -f docker/prod/compose.yaml down
docker compose -f docker/prod/compose.yaml down -v  # also removes local data
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
provider event, never from a client success redirect.

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
