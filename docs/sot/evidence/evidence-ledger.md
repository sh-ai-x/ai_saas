---
doc_id: evidence-ledger
domain: evidence
purpose: Preserve the sources, claims, decisions, counterevidence, and review triggers behind the SOT.
read_when:
  - validating an existing decision
  - changing a provider, framework, security rule, or operational contract
  - reviewing whether a claim is evidence-backed
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
source_of_truth: evidence
owner: platform-engineering
last_reviewed: 2026-09-17
change_impact: high
---

# Evidence Ledger

This ledger is the source of why the SOT makes a decision. It is not a list of
marketing claims. Every record must identify the source, the claim, the
boundary where the claim applies, evidence against it, and the condition that
requires review.

## Record schema

```yaml
record_id: E-000
source_url: https://example.com/official-document
source_type: official-doc | standard | primary-research | baseline-code | measured-test
retrieved_at: YYYY-MM-DD
claim: one testable claim
applicable_boundary: system area and assumptions
decision: accepted | rejected | customized | observed
counterevidence: known limitation or conflicting evidence
revisit_trigger: event that invalidates or ages the claim
```

## Initial records

| ID | Source | Claim and application | Decision |
|---|---|---|---|
| E-001 | [AWS ECS best practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html) | ECS provides documented operational guidance for networking, task definitions, security, scaling, and health checks; applies to the AWS runtime boundary. | accepted as deployment evidence |
| E-002 | [AWS ECS capacity and availability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability-best-practice.html) | Capacity must balance cost against latency/error risk; applies to autoscaling and task sizing, not as a universal numeric target. | accepted with measured thresholds |
| E-003 | [Docker build best practices](https://docs.docker.com/build/building/best-practices/) | Reproducible, small, and safer images reduce runtime risk; applies to image build and release evidence. | accepted |
| E-004 | [FastAPI in containers](https://fastapi.tiangolo.com/deployment/docker/) | Containers are a repeatable packaging boundary for FastAPI services; applies to agent API deployment. | accepted |
| E-005 | [LangGraph reference](https://langchain-ai.github.io/langgraph/reference/) | LangGraph supports stateful, long-running, persistent, streaming, and human-in-the-loop agent workflows; applies to agent orchestration. | accepted for evaluation |
| E-006 | [LangGraph persistence](https://langchain-ai.github.io/langgraphjs/how-tos/cross-thread-persistence-functional/) | Checkpoints support thread state while stores support cross-thread application memory; applies to state separation. | accepted |
| E-007 | [LiteLLM gateway](https://docs.litellm.ai/) | A gateway can unify provider access and expose routing, fallback, spend, and budget controls; applies to model control plane. | accepted as candidate |
| E-008 | [Langfuse observability](https://langfuse.com/docs/observability/overview) | AI traces capture model, prompt, token, latency, tool, retrieval, and evaluation context; applies to AgentOps. | accepted with redaction |
| E-009 | [Langfuse evaluation](https://langfuse.com/docs/evaluation/core-concepts) | Offline datasets and experiments complement online evaluation of production traces; applies to verification loop. | accepted |
| E-010 | [Supabase RAG permissions](https://supabase.com/docs/guides/ai/rag-with-permissions) | pgvector retrieval can be filtered by Postgres RLS; applies to permission-aware RAG, subject to query tests. | accepted with security tests |
| E-011 | [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server) | Server applications use authorization-code exchange and confidential credentials; applies to Google authentication. | accepted |
| E-012 | [Lemon Squeezy webhooks](https://docs.lemonsqueezy.com/help/webhooks) | Webhooks use a signing secret and must be validated against the request; applies to payment event ingress. | accepted |
| E-013 | [Toss Payments API](https://docs.tosspayments.com/en/api-guide) | Idempotency keys make repeated POST attempts return the same result within the provider contract; applies to payment creation. | accepted with sandbox tests |
| E-014 | [Toss Payments webhooks](https://docs.tosspayments.com/en/webhooks) | Asynchronous payment updates are delivered through webhooks with event-specific payloads and documented retries; identity and verification must be chosen per event and payment query. | accepted with event-specific identity |
| E-015 | [Anthropic long-running harness research](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Incremental work and structured artifacts help agents span context windows; applies to modular SOT and handoff design. | accepted |
| E-016 | [Anthropic harness design research](https://www.anthropic.com/engineering/harness-design-long-running-apps) | Separate evaluation, explicit sprint contracts, and structured communication improve complex long-running work; applies as selective escalation, not default complexity. | customized |
| E-017 | Baseline code: `../mysaas/my-saas/src/db/schema/plans.ts:25-70` | A single plan catalog can hold pricing, provider mappings, and quotas; applies as a product baseline to be hardened. | observed baseline |
| E-018 | Baseline code: `../mysaas/my-saas/src/db/schema/credits.ts:19-50` | Credit effects can be preserved as typed transactions with payment identity and metadata; applies as the ledger starting point. | observed baseline |
| E-019 | Baseline code: `../mysaas/my-saas/src/app/api/super-admin/users/[id]/credits/route.ts:69-121` | Admin credit actions can record actor identity and reason; applies as the support-operation starting point. | observed baseline |
| E-020 | Baseline code: `../mysaas/my-saas/src/lib/auth/withSuperAdminAuthRequired.ts:14-50` | A common authorization wrapper can protect admin API operations; applies as an MVP boundary, not final RBAC proof. | observed baseline |
| E-021 | [Martin Fowler: Gateway](https://martinfowler.com/articles/gateway-pattern.html) | An application-owned gateway translates local operations and types to a foreign API and keeps external concepts out of domain logic; applies to the provider adapter boundary. | accepted as architecture evidence |
| E-022 | [Lemon Squeezy webhook guide](https://docs.lemonsqueezy.com/guides/developer-guide/webhooks) | Lemon Squeezy signs webhook requests in `X-Signature`, expects raw-body verification, and retries non-200 responses; applies to the Lemon adapter ingress. | accepted |
| E-023 | [Lemon Squeezy subscription object](https://docs.lemonsqueezy.com/api/subscriptions/the-subscription-object) | Lemon subscription statuses include `on_trial`, `active`, `paused`, `past_due`, `unpaid`, `cancelled`, and `expired`; applies to provider-to-domain status mapping. | accepted with explicit access policy |
| E-024 | [Toss Payments API guide](https://docs.tosspayments.com/en/api-guide) | Toss supports POST idempotency keys, payment confirmation, payment query, and cancellation; applies to one-time payment and refund adapter capabilities. | accepted with sandbox tests |
| E-025 | [Toss Payments webhook events](https://docs.tosspayments.com/reference/using-api/webhook-events) | Toss payment webhook types and proof differ by event; virtual-account callbacks expose payment proof and general payment events expose payment data; applies to event-specific verification. | accepted with server-side query |
| E-026 | [Toss Payments webhook guide](https://docs.tosspayments.com/en/webhooks) | Toss retries webhook delivery when the endpoint does not return HTTP 200, up to seven resends in its documented policy; applies to inbox persistence and replay. | accepted |
| E-027 | [Toss Payments billing integration](https://docs.tosspayments.com/guides/v2/billing/integration) | Toss recurring billing uses billing keys and requires the merchant application to schedule recurring approval calls; applies to the optional recurring-billing capability. | accepted with scheduler ownership |
| E-028 | [Toss Payments API keys](https://docs.tosspayments.com/reference/using-api/api-keys) | Toss separates client and secret keys and distinguishes service/MID key sets; applies to environment and credential boundaries. | accepted |

## Source policy

- Official provider and platform documentation is required for current API,
  security, retry, pricing, and lifecycle claims.
- Primary research informs design patterns but does not prove product-specific
  performance.
- Baseline code explains current intent and existing behavior; tests and
  measured production evidence are required before calling it validated.
- Template documentation is never the sole support for a normative decision.
