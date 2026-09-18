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

## Start locally

The safest quick path is a generated process-only secret that is never written
to Git:

```bash
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m foundation.config \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
python3 -m lib.intent_integrity --pre ai-saas-foundation
python3 -m foundation.server \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
```

In another terminal, check `http://127.0.0.1:8080/healthz`,
`/v1/contracts`, or `/v1/runs/demo/events`. The server validates all required
settings before binding a port and never prints secret values.

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

`python3 scripts/local-smoke.py` runs this flow automatically. It succeeds on
a host without Docker; if Docker Desktop is stopped it records
`docker=blocked (daemon unavailable)` and does not suggest a paid upgrade.

## Docker path

Docker Compose starts the local PostgreSQL companion and the same HTTP surface.
No cloud account, ALB, NAT gateway, Redis, or paid plan is needed.

```bash
cp config/profiles/free-portfolio.example.env .env
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose -f docker/dev/compose.yaml up --build
```

Stop and remove the local database volume with `docker compose -f
docker/dev/compose.yaml down -v` when its disposable development data is no
longer needed.

## Profile checks

`free-portfolio` requires the mock provider, local workflow mode, a generated
secret, and worker disabled. `aws-worker` additionally requires explicit
non-secret worker identifiers and the fixed low-cost boundary: Fargate Spot,
ARM64, 0.25 vCPU, 512 MiB, public-subnet outbound access, and no inbound rules.
Both profiles reject missing settings and paid/always-on ALB, NAT, Redis, or
plan configuration. The AWS example is intentionally incomplete and should
fail until an operator supplies its identifiers:

```bash
python3 -m foundation.config \
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
python3 -m foundation.contract_check
python3 -m unittest discover -s tests -v
```

The complete local gate, including evaluator evidence and Docker Compose
configuration validation, is `scripts/verify-local.sh`. It does not require a
cloud account; if Docker is unavailable it reports the Compose check as
skipped.

Step evidence is compact, valid JSON rather than a raw agent transcript:

```bash
python3 scripts/record-step-outputs.py --all
```

This writes `phases/ai-saas-foundation/step0-output.json` through
`step5-output.json` with the real command exit code, stdout, stderr, and
duration. Docker availability is preserved as an explicit environment note.

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
