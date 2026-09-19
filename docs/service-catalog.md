# Foundation service and module ownership

This step turns the `mysaas` vertical slice into a contract-first modular
monolith. The physical deployment is one local web process plus an optional
local PostgreSQL container; the boundaries below are logical ownership rules
for service extraction.

| Module/service | Owns | Public boundary | Data it may write | Failure behavior |
|---|---|---|---|---|
| `web-console` / `apps/web` | UI, session-aware request shaping, SSE presentation | REST and SSE through the composition root | none directly | return a typed error; never trust browser success for billing |
| `api-gateway` | request correlation and authenticated routing | versioned REST/SSE | none | fail closed when identity or tenant scope is absent |
| `identity-tenant` | users, organizations, memberships, RBAC, OAuth/session policy | identity and tenant REST contracts | identity/membership schema | deny by default; no email-only authorization |
| `project-service` | AI project metadata and provider-config references | project REST contracts | project schema | reject cross-tenant project access |
| `run-service` | run state, idempotency, replay sequence | run REST/SSE and run events | run/event/checkpoint schema | preserve durable state; retry only with idempotency |
| `agent-worker` | bounded execution and checkpoints | `run.requested` consumer | checkpoint/execution schema | interruption is recoverable; no inbound worker API |
| `metering-billing` | reservations, ledger, entitlement, provider registry/inbox | billing REST and normalized provider events | billing/order/inbox/ledger schema | no charge or entitlement without durable proof |
| `admin-operations` | privileged use cases and append-only audit | authenticated admin REST | audit schema | require role, target scope, reason, and idempotency |
| `observability` | redacted correlation and evaluation records | trace/evaluation events | telemetry/evaluation store | telemetry loss must not grant access or block core state |

## Dependency direction

```text
apps/web -> REST/SSE contracts -> composition root -> owned modules
run-service -> provider-neutral metering port -> metering-billing
run-service -> run.requested event -> agent-worker
provider adapters -> provider ports -> normalized events -> billing domain
```

The domain imports only provider capability ports and normalized events. Toss,
Lemon Squeezy, and mock adapter implementations are not part of this step and
must not be imported by domain modules. A service may not write another
service's tables directly.

The web console is intentionally a thin local boundary. Its Next.js route
handler proxies same-origin requests to the composition root, while the
browser only owns presentation state and demo input. Identity, tenant scope,
run durability, credit reservation, webhook verification, and admin audit
records remain server-owned. This preserves the logical MSA ownership model
without physically splitting the free-portfolio deployment.

## Deployment profiles

`free-portfolio` is the default: one web/application process, local or managed
PostgreSQL, and bounded workflow invocations. It explicitly disables the AWS
worker and rejects ALB, NAT, Redis, always-on ECS, and paid Vercel/Cloudflare
plan settings.

`aws-worker` is an optional worker-only boundary. It describes an on-demand
ARM Fargate Spot task with checkpoint/retry requirements, public-subnet outbound
access, and no inbound worker rules. It does not provision a resource, require
ALB/NAT/Redis, or introduce an always-on service. AWS credentials are not part
of the profile; an injected task role is the only supported auth mode.

The machine-readable ownership summary is [ownership.json](ownership.json),
and the versioned wire contracts live under
[`packages/contracts/`](../packages/contracts/).
