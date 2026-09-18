---
doc_id: architecture-system-map
domain: architecture
purpose: Describe the production system boundaries and cross-domain flows.
read_when:
  - changing a service boundary, data flow, provider, or deployment topology
  - evaluating a new feature's failure domains
audience:
  - user
  - agent
  - reviewer
prerequisites:
  - ../00-index.md
source_of_truth: map
owner: platform-engineering
last_reviewed: 2026-09-17
change_impact: high
---

# Production AI Engineering System Map

## Scope

This map covers the boundary between the Next.js product surface, the Python
agent runtime, AI providers, data systems, billing providers, and AWS
operations. It does not define domain-specific prompts or product features.

## Contract

The service boundaries and source-of-truth ownership in this map are
normative. A boundary change must update the owning contract, its failure
domain, and the verification evidence before implementation is considered
complete.

## Baseline topology

```text
Browser
  -> Next.js frontend and streaming UI
  -> authenticated request
  -> AWS ALB
  -> ECS/Fargate FastAPI agent API
  -> queue/worker boundary for long or retryable runs
  -> LangGraph runtime
  -> AI gateway with routing, fallback, and budgets
  -> approved model providers

LangGraph checkpoints -> Postgres-backed run state
Product state        -> Postgres: users, plans, entitlements, credits, events, audit
Retrieval memory      -> Postgres + pgvector with permission-aware queries
Agent traces          -> Langfuse with privacy-safe correlation
Payments              -> signed provider webhooks -> event ledger -> state transitions
Operations            -> ECR -> ECS/Fargate -> ALB/CloudWatch -> runbooks
```

## Service responsibilities

| Boundary | Owns | Must not own |
|---|---|---|
| Next.js | user interaction, auth initiation, streaming presentation, safe request shaping | provider secrets, entitlement truth, unrestricted tool execution |
| FastAPI agent API | authenticated run creation, domain authorization, streaming/async run access | direct browser trust, unbounded model calls |
| LangGraph runtime | graph state, node transitions, checkpointing, tool orchestration | billing truth or ambient credentials |
| AI gateway | provider credentials, model allowlist, routing, fallback, budgets, provider telemetry | product authorization or user entitlement decisions |
| Postgres | users, plans, entitlements, credits, events, audit, durable run metadata | unbounded binary/object storage |
| pgvector | permission-aware retrieval indexes and embeddings | bypassing tenant/document authorization |
| Langfuse | AI traces, prompt/model/tool/evaluation metadata | the product's transactional source of truth |
| Payment adapters | checkout/provider API calls, signature verification, provider mapping | directly trusting client redirects |
| ECS/Fargate | isolated service tasks, scaling, health, deployment runtime | business-level retry or payment state decisions |

## Critical flows

### Authenticated agent run

1. Next.js receives an authenticated user request.
2. FastAPI resolves user/tenant scope and checks entitlement and run limits.
3. The run is created with a durable `run_id` and idempotency key.
4. LangGraph executes bounded nodes and tools, persisting checkpoints.
5. AI gateway applies model policy, budget, timeout, retry, and fallback.
6. Langfuse receives correlated trace data with sensitive payload controls.
7. The result is streamed or retrieved asynchronously; cancellation is durable.

### Payment-to-entitlement flow

1. The client starts checkout, but client success is not entitlement proof.
2. The provider webhook is verified against the raw request body or provider
   event secret.
3. The raw event is persisted and deduplicated.
4. A provider-neutral state transition updates entitlement and/or credits in a
   transaction-safe way.
5. An audit/outbox event records the effect.
6. Reconciliation can replay the event without double-granting access.

## Failure domains

- Frontend outage must not erase durable agent runs or payment events.
- AI provider outage must not bypass model policy or exceed the run budget.
- A worker crash must resume from a checkpoint or surface a recoverable run.
- A duplicate webhook must be a no-op after event deduplication.
- Supabase/Postgres degradation must fail closed for privileged mutations and
  avoid granting new entitlements without durable confirmation.
- Langfuse degradation must not block user responses, but must emit a local
  telemetry-loss signal.
- ECS deployment failure must stop promotion and preserve the last healthy
  revision for rollback.

## Security and cost implications

Keep provider credentials and privileged data behind their owning service
boundary. Capacity, queue depth, model spend, database connections, and
telemetry volume are separate operational budgets; changing one boundary must
not silently move cost or authorization responsibility to another service.

## Verification evidence

- Boundary tests prove browser requests cannot bypass FastAPI authorization or
  provider adapters.
- Contract tests cover the payment event path, entitlement transition, agent
  run creation, and trace correlation across service boundaries.
- Failure-injection tests cover provider outage, worker restart, duplicate
  webhook delivery, database degradation, and ECS rollback.

## Related documents

- [Google OAuth and identity](../auth/google-oauth.md)
- [Subscriptions and entitlements](../billing/subscriptions-and-entitlements.md)
- [Payment webhooks and ledger](../billing/payment-webhooks-and-ledger.md)
- [Agent runtime and tools](../agent/runtime-and-tools.md)
- [AWS and Docker deployment](../operations/aws-docker-deployment.md)
- [Verification, release, and incident response](../verification/release-and-incident.md)

## Sources

- [AWS ECS best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [LangGraph reference](https://langchain-ai.github.io/langgraph/reference/)
- [Langfuse observability](https://langfuse.com/docs/observability/overview)
- [Supabase database and pgvector](https://supabase.com/docs/guides/database/overview)
- Baseline: `../mysaas/my-saas/docker/prod/Dockerfile:1-59`,
  `src/auth.ts:24-35`, `src/app/api/webhooks/stripe/route.ts:429-499`.
