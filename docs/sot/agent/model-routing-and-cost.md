---
doc_id: agent-model-routing-cost
domain: agent
purpose: Define model selection, fallback, retry, budget, and AI cost controls.
read_when:
  - adding a model provider or changing model routing
  - investigating token cost, provider failure, latency, or retry storms
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - runtime-and-tools.md
  - observability-and-evaluation.md
  - ../operations/aws-docker-deployment.md
source_of_truth: contract
owner: agent-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Model Routing and Cost

## Gateway boundary

The agent runtime does not hold provider API keys. An AI gateway such as
LiteLLM is evaluated as the control point for a unified provider interface,
routing, retry/fallback, spend tracking, and project budgets. **(source:
https://docs.litellm.ai/)**

The exact gateway remains replaceable. The contract must survive a provider or
gateway change.

## Routing policy

Routing may consider task class, quality requirement, latency target, provider
health, region, privacy policy, and remaining budget. The policy must be
explicit and observable; a model must not silently escalate to an expensive
provider.

Every request records:

- policy version and selected model/provider
- estimated and actual input/output usage
- user/tenant/project/run correlation
- retry count and fallback reason
- latency and finish reason
- budget before and after the request

## Cost valves

- per-request token/output cap
- per-run step and time cap
- per-user and per-tenant concurrency limit
- per-user/day and project/month budget
- provider-level circuit breaker
- fallback allowlist and fallback budget
- rate limits and queue backpressure
- hard stop when the budget is exhausted

Limits must be configuration, visible in traces, and tested. No hidden retry
loop may consume the remaining budget.

## Failure policy

- Retry only classified transient failures, with bounded exponential backoff.
- Do not retry validation, authorization, payment, or policy-denial failures.
- Fallback only to an approved compatible model and record the reason.
- If all providers fail, return a recoverable error and preserve run state.
- If a response is partial, label it partial; do not mark the run successful.

## Verification evidence

- Routing tests prove allowlist and policy selection.
- Budget tests prove hard stops and no fallback overspend.
- Provider outage tests prove bounded retries and circuit breaking.
- Load tests measure queue delay, p95 latency, provider errors, and cost/run.
- Dashboard queries group spend by tenant, user, model, provider, and feature.

## Sources

- [LiteLLM gateway](https://docs.litellm.ai/)
- [AWS ECS capacity and availability](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/capacity-availability-best-practice.html)
- [Langfuse observability](https://langfuse.com/docs/observability/overview)
