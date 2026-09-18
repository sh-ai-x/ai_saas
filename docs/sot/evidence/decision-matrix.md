---
doc_id: evidence-decision-matrix
domain: evidence
purpose: Compare architecture candidates by reliability, cost, security, complexity, and lock-in.
read_when:
  - replacing a gateway, framework, database, payment provider, or runtime
  - reviewing whether a current choice is still justified
audience:
  - user
  - agent
  - reviewer
prerequisites:
  - ../00-index.md
  - evidence-ledger.md
source_of_truth: evidence
owner: platform-engineering
last_reviewed: 2026-09-17
change_impact: high
---

# Decision Matrix

Scores are directional until measured in the target workload. They are not a
substitute for load, failure, security, or cost tests.

| Decision area | Baseline candidate | Why it fits | Main risk | Required evidence |
|---|---|---|---|---|
| Agent orchestration | Python + FastAPI + LangGraph | Stateful runs, checkpoints, streaming, approvals, explicit graph control. | More runtime concepts than a simple request/response chain. | Scenario, checkpoint-resume, cancellation, and load tests. |
| Model control | LiteLLM or replaceable gateway | Provider abstraction, routing, fallback, spend/budget controls. | Gateway behavior and provider compatibility can drift. | Routing, outage, budget, and latency comparisons. |
| AgentOps | Langfuse | LLM-specific trace, prompt, evaluation, dataset, and production feedback loop. | Sensitive payload retention and added operational surface. | Redaction, export failure, trace completeness, evaluation repeatability. |
| Product data | Supabase Postgres | Relational source of truth and managed operational features. | Connection limits, vendor dependency, RLS mistakes. | Pooling, backup/restore, RLS, migration, and permission tests. |
| Vector memory | Postgres + pgvector | Keeps document permissions near relational data. | Index and recall trade-offs at scale. | Recall/latency, RLS, reindex, and corpus growth tests. |
| Authentication | Google OAuth through Better Auth baseline | Matches `mysaas` user/session/account pattern. | Account-linking, provider outage, and credential handling. | OAuth, session, collision, and protected-route tests. |
| Billing | Ports-and-Adapters with capability-based Lemon Squeezy and Toss adapters | Preserves one domain contract while allowing provider-specific checkout, confirmation, recurring billing, refund, and webhook semantics. | Capability drift, registry misconfiguration, provider-specific state and webhook behavior. | Per-provider sandbox events, signature/query proof, idempotency, ordering, replay, reconciliation, and capability contract tests. |
| Runtime | Docker on AWS ECS/Fargate | Isolated deployment units, health checks, autoscaling, managed task runtime. | AWS configuration and minimum-cost topology complexity. | Image, deployment, rollback, scaling, and failure-injection tests. |

## Current decisions

- Prefer the candidate when its required evidence passes.
- Keep adapter boundaries for providers and gateways.
- Record measured results as new evidence records rather than overwriting the
  original decision.
- Reopen a decision when a source changes, a threshold is exceeded, an
  incident reveals a missing assumption, or a better measured option appears.
