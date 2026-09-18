---
doc_id: sot-index
domain: architecture
purpose: Route users and agents to the smallest relevant SOT document set.
read_when:
  - starting any implementation, review, support, or incident task
  - deciding which SOT documents belong in an agent context
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites: []
source_of_truth: map
owner: platform-engineering
last_reviewed: 2026-09-17
change_impact: high
---

# SOT Index

This is the canonical entrypoint for the production AI Engineering SOT. The
SOT is a modular Markdown library, not a monolithic document. Read this index
first, select the primary document for the task, then read only the related
documents required by that document's contract.

## SOT model

- **Design maps** explain boundaries, flows, state, dependencies, and failure
  domains.
- **Operational contracts** define what code, agents, operators, and providers
  must guarantee.
- **Evidence ledgers** explain why a decision exists, which source supports it,
  where it applies, and when it must be revisited.

## Routing rules

1. Match the task to the `read_when` trigger below.
2. Read the primary document completely before proposing a change.
3. Read its listed related documents before touching a cross-domain boundary.
4. If two contracts conflict, stop and report the conflict; do not silently
   choose one.
5. Cite the `doc_id` and relevant section in the task handoff.
6. If a provider feature, security rule, or price may have changed, read the
   evidence ledger and verify the linked official source again.

## Functional routing

| Task or situation | Primary document | Related documents |
|---|---|---|
| Change system boundaries or data flow | [architecture/system-map.md](architecture/system-map.md) | [operations/aws-docker-deployment.md](operations/aws-docker-deployment.md) |
| Implement Google login or session handling | [auth/google-oauth.md](auth/google-oauth.md) | [security/safety-boundaries.md](security/safety-boundaries.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Change plans, quotas, or entitlement access | [billing/subscriptions-and-entitlements.md](billing/subscriptions-and-entitlements.md) | [billing/payment-webhooks-and-ledger.md](billing/payment-webhooks-and-ledger.md), [admin/operations-and-audit.md](admin/operations-and-audit.md) |
| Add or change provider adapter capability | [billing/provider-adapter-architecture.md](billing/provider-adapter-architecture.md) | [billing/payment-webhooks-and-ledger.md](billing/payment-webhooks-and-ledger.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Integrate or debug Lemon Squeezy | [billing/providers/lemon-squeezy.md](billing/providers/lemon-squeezy.md) | [billing/provider-adapter-architecture.md](billing/provider-adapter-architecture.md), [billing/payment-webhooks-and-ledger.md](billing/payment-webhooks-and-ledger.md), [billing/subscriptions-and-entitlements.md](billing/subscriptions-and-entitlements.md) |
| Integrate or debug Toss Payments | [billing/providers/toss-payments.md](billing/providers/toss-payments.md) | [billing/provider-adapter-architecture.md](billing/provider-adapter-architecture.md), [billing/payment-webhooks-and-ledger.md](billing/payment-webhooks-and-ledger.md), [billing/subscriptions-and-entitlements.md](billing/subscriptions-and-entitlements.md) |
| Reconcile or compare multiple payment providers | [billing/payment-webhooks-and-ledger.md](billing/payment-webhooks-and-ledger.md) | [billing/provider-adapter-architecture.md](billing/provider-adapter-architecture.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Operate a user, plan, or credit account | [admin/operations-and-audit.md](admin/operations-and-audit.md) | [billing/subscriptions-and-entitlements.md](billing/subscriptions-and-entitlements.md), [security/safety-boundaries.md](security/safety-boundaries.md) |
| Add or change an agent tool | [agent/runtime-and-tools.md](agent/runtime-and-tools.md) | [security/safety-boundaries.md](security/safety-boundaries.md), [agent/observability-and-evaluation.md](agent/observability-and-evaluation.md) |
| Change model routing or AI spend limits | [agent/model-routing-and-cost.md](agent/model-routing-and-cost.md) | [agent/observability-and-evaluation.md](agent/observability-and-evaluation.md), [operations/aws-docker-deployment.md](operations/aws-docker-deployment.md) |
| Change memory, RAG, or vector search | [agent/memory-and-retrieval.md](agent/memory-and-retrieval.md) | [security/safety-boundaries.md](security/safety-boundaries.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Investigate agent quality, cost, or latency | [agent/observability-and-evaluation.md](agent/observability-and-evaluation.md) | [agent/model-routing-and-cost.md](agent/model-routing-and-cost.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Deploy, scale, or recover AWS services | [operations/aws-docker-deployment.md](operations/aws-docker-deployment.md) | [architecture/system-map.md](architecture/system-map.md), [verification/release-and-incident.md](verification/release-and-incident.md) |
| Handle prompt injection, data leakage, or unsafe tools | [security/safety-boundaries.md](security/safety-boundaries.md) | [agent/runtime-and-tools.md](agent/runtime-and-tools.md), [agent/memory-and-retrieval.md](agent/memory-and-retrieval.md) |
| Define release evidence or respond to an incident | [verification/release-and-incident.md](verification/release-and-incident.md) | [evidence/evidence-ledger.md](evidence/evidence-ledger.md) |
| Validate or change an architectural decision | [evidence/evidence-ledger.md](evidence/evidence-ledger.md) | [architecture/system-map.md](architecture/system-map.md) |

## Document contract

Every SOT document must retain the front matter fields `doc_id`, `domain`,
`purpose`, `read_when`, `audience`, `prerequisites`, `source_of_truth`,
`owner`, `last_reviewed`, and `change_impact`.

Functional design-map and operational-contract documents must state scope,
contract, normal flow, failure flow, security/cost implications, verification
evidence, related documents, and sources. The index is the routing contract;
the evidence ledger and decision matrix use their own record and comparison
schemas instead of repeating operational-flow sections. The runbook is a
short operator navigation layer and must link back to the owning contracts.

## Baseline rule

`../mysaas` is the primary implementation baseline for auth, plans,
subscriptions, credits, webhooks, admin operations, observability, and Docker.
It is not normative proof of production completeness. Template repositories are
not authoritative sources.
