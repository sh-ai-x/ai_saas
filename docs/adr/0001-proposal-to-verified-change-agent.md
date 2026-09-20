---
adr: 0001
title: Proposal-to-Verified-Change Agent architecture
status: proposed
date: 2026-09-20
decision_owner: product-and-platform
scope: new-private-product-repository
source_of_truth: architecture-decision
related_sot: ../../.dev-kit/hand-off/sot-harness-proposal-to-verified-change-agent-20260920.md
related_decision_log: ../../.dev-kit/decision-log-sot-harness/proposal-to-verified-change-agent-20260920.md
---

# ADR-0001: Proposal-to-Verified-Change Agent architecture

## Status

Proposed. This ADR becomes accepted only after the evidence-plan proposal is
reviewed and explicitly approved. It records the architecture for the new
private product repository; it does not silently change the existing
foundation repository's runtime.

## Context

Teams can write a proposal or PRD, but the path from requirements to a safe,
reviewable code change is fragmented. A generic document summarizer or RAG
chatbot does not prove that requirements were mapped to code, that a proposed
patch is authorized, or that tests actually support the result. An unrestricted
coding agent creates a larger safety, cost, and evaluation surface than this
portfolio product needs.

The product therefore needs one narrow outcome:

> Turn an approved proposal and an authorized repository into an
> evidence-backed, reviewable, sandbox-verified change package.

The package contains the parsed requirements, repository evidence, plan,
approval record, patch/diff, verification results, evaluation scores, and
trace identifiers. The system may use an LLM for interpretation and bounded
tool selection, but policy, authorization, lifecycle state, metering, and
completion status must remain deterministic and server-owned.

## Decision

Build a **Proposal-to-Verified-Change Agent**, implemented as a bounded,
durable workflow:

```text
proposal -> inventory -> targeted evidence -> analyze -> plan
         -> human approval -> sandbox patch -> tests -> evaluate -> report
```

The initial product is a small MSA-shaped deployment behind Nginx:

```text
Browser
  -> Nginx (TLS, routing, limits, SSE)
  -> Web Console / Control API
  -> Agent Orchestrator
  -> Sandbox Worker
  -> Signed Git/CI Delivery Adapter
  -> PostgreSQL + redacted LangSmith traces/evaluations
```

The first deployment may use Docker Compose and one PostgreSQL deployment with
schema ownership boundaries. Physical extraction, a broker, Kubernetes, and a
service mesh are deferred until measured workload or isolation evidence
justifies them.

V1 is capability-driven. Every Git repository can receive inventory, evidence,
and a plan. A profile scanner proposes a validated `change-assurance.yaml`
declaring allowed paths, test command, resource limits, and retention profile.
Node/pnpm and Python/pytest adapters provide verified execution initially; an
adapter SDK and conformance pack provide the extension path. Unknown runtimes
remain `plan_only` rather than receiving a false `verified` label.

After verification, a signed Git/CI delivery adapter can create a branch/PR or
dispatch a policy-approved delivery request using scoped credentials. The
agent never receives ambient merge or deploy authority.

## Runtime profiles

The contracts are identical across two deployment profiles.

### Local Lite — 8GB MacBook Air

- at most two long-lived processes: web/control API and orchestrator;
- SQLite checkpoints and audit state;
- filesystem path/symbol index, no vector database;
- bounded sandbox subprocess, not a long-lived worker;
- remote model API with allowlisted/redacted context or deterministic fake
  provider;
- redacted LangSmith API traces, no local collector;
- no Docker Desktop, PostgreSQL, Redis, Kafka, Nginx, or local model server.

Local Lite passes only when application peak RSS is `<= 3GB`, long-lived
application processes are `<= 2`, and no Docker daemon, local model process, or
swap-inducing background service is required. Untrusted high-impact execution
is disabled locally.

### Production MSA

Nginx, Control API, Agent Orchestrator, Sandbox Worker, Delivery Adapter, and
PostgreSQL are separately deployable boundaries. This profile provides the
production isolation and failure-domain evidence; Local Lite provides the
resource-bounded developer experience.

## Pivot boundary

The reusable Agent Platform Kernel owns versioned contracts, tenant/policy
authorization, run/checkpoint state, approval, metering, audit, sandbox
protocol, evaluation ledger, metric rules, and runtime profiles.

`project-packs/proposal-to-verified-change/` owns project-specific prompts,
requirement extensions, retrieval ranking, tools, adapters, report copy, and
datasets. The kernel imports ports only; it never imports a Project Pack. Packs
are resolved through a versioned registry, cannot write kernel tables directly,
and must pass conformance tests. The detailed replacement procedure is defined
in [Project Pivot Contract](../architecture/project-pivot-contract.md).

## Token and cost boundary

The kernel owns `TokenBudgetPort`, context caching, provider usage
reconciliation, and hard-stop behavior. Budgets apply per tenant, run, node,
model call, context, timeout, retry, and cost. A Project Pack can provide
prompt templates or retrieval hints, but cannot raise a configured budget.

Local Lite begins with a small-repository profile: `20,000` total model tokens
for plan-only runs, `41,000` maximum for verification runs including the
bounded patch retry, at most `8,000` input tokens per call, and five primary
calls plus one bounded patch retry. The
context pipeline uses deterministic indexing, authorized path/symbol selection,
line-preserving truncation, content-addressed summaries, and one
evidence-triggered expansion. Retries receive compact failure context rather
than the full transcript.

Budget exhaustion produces `quota_paused` or `budget_exceeded`; it cannot
silently truncate evidence or produce `verified`. Usage records distinguish
exact provider counts from estimates. Token savings are compared on identical,
versioned evaluation cases and are accepted only when correctness, grounding,
safety, and required-test gates are unchanged or better. The normative details
are in [Token Budget Contract](../architecture/token-budget-contract.md) and
the measurable release fields are in [Change-Assurance Metrics Contract](../metrics/change-assurance-metrics.md).

## Framework placement

The three requested Lang* technologies are used because their responsibilities
are different and independently testable, not because every layer needs an
agent abstraction.

| Layer | Owns | Must not own | Why this is appropriate |
| --- | --- | --- | --- |
| LangChain | provider adapters, prompts, structured output schemas, retrievers, typed tools | tenant auth, billing, lifecycle authority, final success | model/tool boundaries need typed parsing and explicit capabilities |
| LangGraph | bounded graph, routing, checkpointing, retry, interrupt/resume, state events | ambient credentials, payment truth, authorization policy | the run can pause for approval and resume after worker failure |
| LangSmith | redacted traces, datasets, offline/online evaluators, regression comparison | product database, authorization, billing ledger | quality and safety must be measured against versioned evidence |
| Nginx | TLS termination, route proxying, rate/request limits, SSE transport | workflow/business logic | edge transport is stable without coupling it to agent state |

LangChain is not used as a hidden autonomous loop. LangGraph is not used as a
replacement for the product run database. LangSmith is not used as the source
of truth for permissions or user-visible completion.

## Workflow and authority contract

The authoritative product lifecycle is:

```text
created -> inventorying -> analyzing -> planning -> waiting_approval
         -> patching -> testing -> evaluating
         -> completed | failed | cancelled | quota_paused | plan_only

`completed -> delivery_requested -> delivery_ready | delivery_failed` is an
optional post-verification path. Delivery failure never changes the recorded
verification result.
```

Deterministic nodes own authorization, path/network policy, usage budgets,
transition validity, idempotency, and verification gates. LLM nodes may return
only validated schemas. Retrieved repository text is untrusted data and cannot
grant permissions or alter the system prompt.

The default tool posture is read-only. File writes, patch application, test
execution with side effects, network calls, issue creation, merge, and deploy
are typed capabilities with explicit policy. High-impact actions pause at a
LangGraph approval interrupt, record the approver and scope, and resume only
with a valid approval token.

The graph has a profile-validation gate before patching. It exposes no
arbitrary shell tool, model-generated network destination, vector database, or
silent provider fallback in v1.

Static policy may auto-approve low-risk delivery. High-impact delivery pauses
once for explicit approval and records the approver, scope, and adapter run.

## Reliability and release decision

Every completed run emits a machine-readable report. The release dataset
contains normal, ambiguous, incomplete, and prompt-injection cases. Results
are stored with dataset version, evaluator version, model/prompt version,
sample count, denominator, and failed examples.

The initial release gates are:

- requirement coverage recall `>= 0.95`; critical requirements `= 1.00`;
- acceptance-criteria coverage `>= 0.95`;
- evidence precision `>= 0.98`; critical evidence precision `= 1.00`;
- unsupported claim rate `<= 0.02`; unsupported critical claims `= 0`;
- invalid reference rate `= 0` for a completed change package;
- all required tests and acceptance checks pass before `verified`;
- expected calibration error `<= 0.10`, reported per evaluation batch;
- Local Lite token ceilings and model-call limits are enforced with
  `budget_overrun_rate = 0`; the initial optimized profile targets at least
  `30%` token savings against a fixed baseline without any quality or safety
  regression;
- small-fixture p95 latency `<= 120s` for plan-only and `<= 600s` for
  patch-plus-test runs;
- unauthorized side effects, approval bypass, secret leakage, cross-tenant
  access, sandbox escape, disallowed network access, high-impact policy false
  negatives, and prompt-injection success are all `0` on release fixtures.

Local Lite additionally gates application peak RSS `<= 3GB`, at most two
long-lived processes, no required Docker daemon, and no required local model
process. Production resource SLOs are measured separately.

Evaluation is code-owned: sanitized failed cases become versioned regression
candidates and are replayed in CI. LangSmith receives redacted metadata for
traces and evaluator comparison; it is not a manual maintenance authority.

The exact formulas, event vocabulary, minimum sample counts, Wilson/bootstrap
confidence policy, and release-report schema are normative in
`docs/metrics/change-assurance-metrics.md`. A release is `pass` only when the
evaluation ledger has persisted the report; missing or undersampled evidence is
`insufficient_sample`.

Metrics with incompatible denominators are not averaged. A zero denominator
is `not_applicable`, never a perfect score. Human acceptance is monitored but
does not replace deterministic checks or security gates.

## Security, safety, and AI ethics

- Tenant and repository authorization is checked server-side before every
  retrieval and tool call.
- The repository manifest is validated before patching or test execution.
- External network access is denied by default and explicitly allowlisted.
- Sandboxes enforce path, process, time, memory, output, and network limits.
- Secrets, raw credentials, and unredacted source are excluded from LangSmith
  traces by default; trace export failure cannot grant authority or block the
  local audit record.
- The interface identifies the system as an AI agent, shows evidence and
  uncertainty, exposes approval boundaries, and never claims a test passed
  without recorded test evidence.
- Retention and deletion rules apply to proposals, source references, traces,
  evaluation records, and generated patches.
- Red-team fixtures cover prompt injection, path traversal, command injection,
  poisoned repository instructions, secret exfiltration, and cross-tenant
  access.

## Alternatives considered

### Generic document/RAG agent

Rejected as the product center. Retrieval is required internally, but a summary
or answer is not a differentiated, verifiable business outcome.

### Unrestricted autonomous coding agent

Rejected for v1. It makes authorization, hallucination, side effects, and
evaluation boundaries unclear. The bounded change package provides a smaller
and more defensible reliability claim.

### Multi-agent swarm

Rejected for v1. It adds coordination and attribution complexity before the
single workflow has a reliable evaluation baseline.

### Queue-first full MSA with separate database per service

Rejected for v1. It increases operational cost and failure modes before the
workflow's latency, isolation, and volume justify physical decomposition.

### LLM-as-a-judge-only verification

Rejected. Semantic evaluators are useful for plan quality, but paths,
permissions, patches, tests, secrets, and side effects require deterministic
checks.

### Fixed two-language product with no extension contract

Rejected. Node/pnpm and Python/pytest are the first verified adapters, but a
capability manifest and conformance SDK allow future runtimes without changing
the workflow, evidence schema, or safety boundary.

## Consequences

Positive:

- one clear portfolio narrative: proposal to evidence-backed verified change;
- LangChain, LangGraph, and LangSmith each have a necessary, non-overlapping
  responsibility;
- correctness and hallucination become measurable rather than marketing
  claims;
- human approval and sandbox boundaries make side effects reviewable;
- any Git repository can receive a useful plan, while verified execution and
  delivery expand through testable adapters;
- delivery automation is available through scoped Git/CI adapters without
  granting ambient credentials;
- the portfolio demo runs on an 8GB MacBook Air without emulating production
  infrastructure;
- the design can start small while preserving extraction boundaries.

Accepted costs:

- LangSmith usage and trace redaction add operational cost;
- high-impact approval remains a deliberate safety boundary;
- provider-specific Git/CI configuration is required, while the adapter
  contract and local simulator keep that configuration bounded;
- Local Lite is intentionally not the production isolation boundary.

## Change triggers

Revisit this ADR if any of the following becomes true:

- direct provider-specific merge or production deployment semantics bypassing
  the signed delivery adapter enter scope;
- external API actions or credential use become required;
- the supported repository size or language set changes materially;
- a new execution adapter, provider fallback, or external action is proposed;
- p95 latency or queue depth breaches the release fixture budget;
- a tenant, data-residency, or compliance requirement forbids the selected
  LangSmith deployment mode;
- measured workload justifies a broker, physical service extraction, or
  per-service data boundary.

## Evidence

- [SOT harness — Proposal-to-Verified-Change Agent](../../.dev-kit/hand-off/sot-harness-proposal-to-verified-change-agent-20260920.md)
- [SOT decision log](../../.dev-kit/decision-log-sot-harness/proposal-to-verified-change-agent-20260920.md)
- [Change-Assurance Metrics Contract](../metrics/change-assurance-metrics.md)
- [Token Budget Contract](../architecture/token-budget-contract.md)
- [Project Pivot Contract](../architecture/project-pivot-contract.md)
- [LangChain Learn](https://docs.langchain.com/oss/python/learn)
- [LangGraph reference](https://langchain-ai.github.io/langgraph/reference/)
- [LangGraph checkpoints](https://langchain-ai.github.io/langgraph/reference/checkpoints/)
- [LangGraph interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)
- [LangSmith evaluation types](https://docs.langchain.com/langsmith/evaluation-types)
- [Anthropic — Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic — Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents)
- [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [NGINX reverse proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy)
- [Microsoft microservices architecture](https://learn.microsoft.com/en-us/azure/architecture/microservices/)
