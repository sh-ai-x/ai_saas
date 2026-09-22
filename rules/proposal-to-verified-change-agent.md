# Proposal-to-Verified-Change Agent — Rule

> Permanent rule record of the accepted proposal. Original source: `docs/proposals/applied/proposal-to-verified-change-agent/idea-proposal-to-verified-change-agent.yaml` (PR #33).

- **Status**: accepted
- **Date**: 2026-09-20
- **Started**: 2026-09-21
- **Tags**: ai-agent, change-assurance, langchain, langgraph, langsmith, msa, ai-security, evaluation

---

## 1. The one agent and the problem it solves

**Agent:** Proposal-to-Verified-Change Agent.

**Problem:** a proposal can be understood by a model yet still produce a change that misses requirements, cites nonexistent code, leaks secrets, bypasses approval, or reports passing tests that were never run. This agent closes that gap by returning a reviewable change package with evidence and a clear failure state.

It is not sold as "AI writes code." It is sold as "AI makes a proposed engineering change traceable and verifiable before a human merges it."

This follows the research recommendation to prefer a bounded workflow when the task has a predictable shape. See [Anthropic — Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents), fetched_at `2026-09-20`, source_type `primary-engineering-guidance`.

## 2. Why the three Lang* frameworks are not over-engineering

| Layer | Responsibility | Evidence that the layer is needed |
|---|---|---|
| LangChain | structured model output, retrievers, typed read-only tools | model boundaries must produce validated domain objects |
| LangGraph | explicit state graph, checkpoint, retry, approval interrupt, resume | patch/test work can outlive a request and pause for a human |
| LangSmith | redacted traces, datasets, offline regression, online sampling | quality claims need repeatable evidence across model/prompt versions |

The choice is intentionally narrow. LangChain does not own authorization; LangGraph does not replace the product run database; LangSmith does not decide billing, permissions, or completion. This avoids using three frameworks for the same responsibility.

Sources: [LangChain Learn](https://docs.langchain.com/oss/python/learn), [LangGraph checkpoints](https://langchain-ai.github.io/langgraph/reference/checkpoints/), and [LangSmith evaluation types](https://docs.langchain.com/langsmith/evaluation-types), each fetched_at `2026-09-20`, source_type `official-documentation`.

## 3. V1 scope that actively removes failure modes

The proposal minimizes trade-offs through capability tiers rather than a fixed language whitelist:

1. **Analyze:** every Git repository can be inventoried and receive an evidence-backed plan.
2. **Verify:** the profile scanner generates `change-assurance.yaml`; the user confirms the capabilities, then a built-in Node/pnpm or Python/pytest adapter runs bounded patch/test verification.
3. **Deliver:** a signed Git/CI adapter creates a branch/PR and can dispatch a policy-approved delivery request using scoped credentials.

Unknown runtimes stop at `plan_only`, never at a misleading `verified`. The adapter SDK and conformance pack make new runtimes an additive extension rather than a redesign. Evaluation-as-code automatically sanitizes failed cases into regression candidates, runs them in CI, and sends only redacted metadata to LangSmith. Low-risk delivery can be auto-approved by static policy; high-impact delivery has one explicit approval interrupt.

## 4. Accuracy and hallucination are release gates

Every completed run emits a machine-readable report, not just a prose answer. The release dataset includes normal, ambiguous, incomplete, and prompt-injection cases. Initial gates are:

- requirement coverage recall `>= 0.95`; critical requirements `= 1.00`;
- acceptance-criteria coverage `>= 0.95`;
- evidence precision `>= 0.98`; critical evidence precision `= 1.00`;
- unsupported claim rate `<= 0.02`; unsupported critical claims `= 0`;
- invalid reference rate `= 0` for a completed package;
- expected calibration error `<= 0.10`, reported per evaluation batch;
- all required tests pass before a package is labelled `verified`.

A zero denominator is `not_applicable`, never a perfect score. A failed gate yields `failed` or `needs_review`, not a confident-looking success. A verified package can continue to the signed delivery adapter; delivery failure never changes the recorded verification result. LangSmith evaluators measure semantic quality, while deterministic checks resolve paths, authorization, schemas, patches, test results, and policy.

See [Anthropic — Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), fetched_at `2026-09-20`, source_type `primary-engineering-guidance`.

## 5. Latency, safety, security, and ethics

Latency is reported end-to-end and per node as p50/p95, together with queue delay, sandbox startup, model calls, tokens, cost, retries, and checkpoint resume time. The small-repository release fixture targets p95 `<= 120s` for plan-only and `<= 600s` for patch-plus-test runs. Results are never averaged across incompatible repository sizes.

Local Lite also records peak RSS, process count, Docker daemon state, local model process state, and swap pressure. The laptop release gate is application peak RSS `<= 3GB`, at most two long-lived processes, and no required background infrastructure service. Production resource SLOs are measured separately and never presented as laptop results.

Zero-tolerance release checks cover unauthorized side effects, approval bypass, secret leakage, cross-tenant access, sandbox escape, disallowed network access, high-impact policy false negatives, and prompt-injection success. The UI identifies the agent, shows evidence and uncertainty, exposes approval boundaries, supports deletion/retention policy, and never fabricates a test result or confidence claim.

Sources: [Anthropic — Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents) and [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf), fetched_at `2026-09-20`, source_type `primary-research-guidance` and `government-standard-guidance` respectively.

## 6. Minimal MSA and Nginx boundary

Nginx terminates TLS, routes requests, enforces request limits, and carries non-buffered SSE. It contains no workflow or business logic.

The Web Console and Control API own user interaction, tenant scope, metering, approvals, and lifecycle authority. The Agent Orchestrator owns the LangGraph execution. The Sandbox Worker owns isolated patch/test execution. PostgreSQL is one deployment initially, with schema ownership boundaries and versioned contracts; physical databases, Kafka, a vector database, and a service mesh are deferred. A Delivery Adapter receives only a verified package and scoped policy decision; it creates a signed branch/PR or dispatches CI, never ambient deployment access.

This is enough MSA evidence for a portfolio: explicit ownership, failure boundaries, versioned contracts, worker isolation, and a clear extraction path. It avoids operational ceremony that has no measured benefit in v1. See [NGINX reverse proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy) and [Microsoft microservices architecture](https://learn.microsoft.com/en-us/azure/architecture/microservices/), fetched_at `2026-09-20`, source_type `official-documentation`.

## 7. 8GB MacBook Air Local Lite profile

The laptop profile is a first-class acceptance target, not a reduced afterthought:

| Resource | Local Lite policy |
|---|---|
| Long-lived processes | At most two: web/control API and orchestrator; sandbox is a bounded subprocess |
| State | SQLite for run/checkpoint/audit state; filesystem index for repository context |
| Model | Remote provider API with allowlisted/redacted context or deterministic fake provider; no local model server |
| Observability | Redacted LangSmith API traces; no local collector |
| Infrastructure | No Docker Desktop, PostgreSQL, Redis, Kafka, vector DB, or Nginx required locally |
| Retrieval | bounded path/symbol index; no embeddings or vector service |
| Safety | only allowlisted fixture commands locally; untrusted high-impact execution uses Production Sandbox Worker |

The local acceptance gate is measured on a clean 8GB profile: application peak RSS `<= 3GB`, no more than two long-lived application processes, no Docker daemon, no local model process, and no swap-inducing background service. The test fixture, prompt, and repository size are recorded with the measurement. Production MSA keeps the same contracts but moves Nginx, PostgreSQL, sandbox isolation, and delivery adapters to separate deployable boundaries.

This preserves the portfolio's MSA story without forcing an 8GB laptop to emulate production infrastructure. The design follows the principle that durable workflow state and authorization remain explicit while deployment topology varies by operating profile.

## 8. Project pivot boundary — kernel plus replaceable Project Pack

The workflow is not hard-coded as the whole product. The Agent Platform Kernel owns versioned contracts, tenant/policy authorization, run state, LangGraph checkpointing, approval, metering, audit, sandbox protocol, evaluation ledger, Local Lite/Production profiles, and metric rules.

`project-packs/proposal-to-verified-change/` owns only project-specific prompts, requirement extensions, retrieval ranking, tools, execution and delivery adapters, report copy, and datasets. The kernel imports ports; it never imports a Project Pack. The web/API resolves packs through a registry, and packs cannot write kernel tables directly.

A pivot therefore means adding or removing a pack and running its conformance suite. The kernel must still build, health-check, and pass tenant/security/metric contract tests with no pack installed. This keeps the current proposal valuable without locking the future product to one domain.

## 9. Production Readiness Gate — measurable, not aspirational

"Production-ready" is defined by judgment-capable operational contracts, not feature count. Every run writes the following events to the append-only event ledger: `run.created`, `profile.detected`, `requirement.parsed`, `evidence.emitted`, `tool.authorized`, `approval.decided`, `patch.applied`, `test.completed`, `evaluation.completed`, `report.emitted`, `delivery.requested`, and `run.resumed`.

Each metric stores its formula, numerator, denominator, dataset/version, model/prompt version, sample count, 95% confidence interval, and failed case IDs. Ratios use Wilson 95% confidence interval; latency/resource uses bootstrap 95% upper bound. Insufficient samples yield `insufficient_sample`, never `pass`.

Production Readiness requires all of the following to pass:

- tenant isolation, approval bypass, unauthorized side effect, secret leakage, sandbox escape, prompt-injection success: `0`;
- requirement coverage recall lower bound `>= 0.95`, evidence precision lower bound `>= 0.98`, invalid reference `0`;
- checkpoint resume, SSE replay, terminal-state consistency, and delivery/verification separation: `1.00` on release fixtures;
- required tests pass before `verified` is rendered;
- Local Lite peak RSS `<= 3GB`, long-lived process `<= 2`;
- every release report is reproducible from persisted evidence.

LangSmith is used for redacted trace/evaluator comparison, while the product evaluation ledger remains the authority for release status. This follows [LangSmith evaluation types](https://docs.langchain.com/langsmith/evaluation-types), fetched_at `2026-09-20`, source_type `official-documentation`.

## 10. Token efficiency is a reliability budget

Token optimization is owned by the Agent Platform Kernel, not hidden in project prompts. A `TokenBudgetPort` applies tenant, run, node, context, call, timeout, retry, and cost limits. A Project Pack may request a smaller budget or provide retrieval hints, but it cannot increase the budget. When a ceiling is reached the run becomes `quota_paused` or `budget_exceeded`; it never silently truncates evidence or renders `verified`.

Local Lite starts with a measured small-repository profile: plan-only runs are capped at `20,000` total model tokens, verification runs at `41,000` maximum including the bounded patch retry, one call receives at most `8,000` input tokens, and the graph allows at most five primary calls plus one bounded patch retry. The pipeline uses deterministic repository indexing, authorized path/symbol selection, line-preserving token limits, content-addressed summaries, and one evidence-triggered retrieval expansion. Retries receive only the failure code, missing evidence IDs, and compact repair context.

The metric contract records exact or estimated input/output tokens, model calls, context cache hits, retrieval expansions, budget decisions, token savings against a fixed baseline, and quality per 1,000 tokens. The initial optimization target is at least 30% token savings on the same evaluation cases, but it is accepted only if requirement coverage, evidence precision, unsupported-claim, critical safety, and test gates remain at least as strong. See [Token Budget Contract](../../architecture/token-budget-contract.md) and [Change-Assurance Metrics Contract](../../metrics/change-assurance-metrics.md).

## 11. Review decision and next hand-off

This proposal is approved for implementation. The product outcome, capability tiers, signed delivery boundary, layer contracts, token budgets, quantitative gates, and minimal MSA direction are locked for planning and build. The plan must emit the canonical PRD and phase artifacts before the build runner starts.

`/dev-kit:build` may implement source code only from those phase artifacts. Private-repository creation, remote configuration, and push remain separate authorized delivery actions.

---

## Rule summary (binding)

These are the durable rules any implementation of this proposal must satisfy:

- **R1 (One agent, bounded workflow):** Proposal-to-Verified-Change is the single user-facing agent outcome. No multi-agent swarm. No generic document chatbot as the product center.
- **R2 (Layer ownership):** LangChain owns structured model output and typed read-only tools; LangGraph owns durable workflow state, checkpoint, retry, approval interrupt, and resume; LangSmith owns redacted trace/evaluation only. No layer may take over another's responsibility.
- **R3 (Capability tiers):** Every Git repository supports Analyze; Verify requires a built-in Node/pnpm or Python/pytest adapter or a user-confirmed profile; Deliver requires a signed Git/CI adapter and policy decision. Unknown runtime ⇒ `plan_only`, never `verified`.
- **R4 (Approval gate):** High-impact delivery requires one explicit human approval interrupt. Approval bypass = release-blocker. No ambient merge or deploy credentials.
- **R5 (Release gates — accuracy):** requirement coverage recall `>= 0.95`, evidence precision `>= 0.98`, unsupported claim rate `<= 0.02`, invalid reference `= 0`. Critical safety gates are exactly `1.00` / `0`.
- **R6 (Release gates — latency):** small-repository p95 `≤ 120s` plan-only, `≤ 600s` patch-plus-test. Local Lite peak RSS `≤ 3GB`, ≤ 2 long-lived processes, no Docker daemon, no local model.
- **R7 (Zero-tolerance checks):** unauthorized side effects, secret leakage, cross-tenant access, sandbox escape, disallowed network access, high-impact policy false negatives, and prompt-injection success must all be `0`. Any single occurrence blocks release.
- **R8 (Token budget):** plan-only `≤ 20,000`, verify `≤ 41,000` (including one bounded patch retry), per-call input `≤ 8,000`. Quota exceeded ⇒ `quota_paused` or `budget_exceeded`, never silent truncation.
- **R9 (Kernel / Project Pack boundary):** kernel imports ports only; Project Packs are replaceable via a versioned registry; packs cannot write kernel tables directly.
- **R10 (Evaluation-as-code):** versioned datasets, automatic sanitized failure candidates, deterministic checks, and LangSmith regression runs in CI. Product evaluation ledger is the release authority; LangSmith is comparison/trace only.
- **R11 (Local Lite profile):** at most two long-lived processes, SQLite state, filesystem sandbox, remote model calls, redacted LangSmith traces, no Docker Desktop / Postgres / Redis / Kafka / vector DB / local model / Nginx required.
- **R12 (Production MSA):** Nginx edge proxy only; separately deployable API / orchestrator / sandbox / delivery boundaries; PostgreSQL schema ownership boundaries with versioned contracts.
- **R13 (Metric ledger):** every metric stores formula, numerator, denominator, dataset/version, model/prompt version, sample count, 95% CI, failed case IDs. Zero denominator ⇒ `not_applicable`, never a perfect score. Insufficient sample ⇒ `insufficient_sample`, never `pass`.
- **R14 (Hand-off):** `/dev-kit:build` consumes only PRD and phase artifacts. Private-repository creation, remote configuration, and push remain separate authorized delivery actions.

## Out-of-scope reminders

- Generic document summarization as the product center.
- Multi-agent swarm, ambient credentials, arbitrary external API action, provider fallback, unscoped delivery.
- Arbitrary shell commands, vector database infrastructure, model-generated network destinations.
- Local LLM serving, always-on Docker Desktop, local PostgreSQL / Redis / Kafka, production-grade sandbox isolation on the 8GB laptop.
- Project-specific logic imported directly into kernel modules or cross-pack table writes.
- Kubernetes, Kafka, service mesh, per-service databases in the first deployment.

## Limitations

- The agent never receives ambient merge or deploy credentials; all delivery is delegated to scoped, auditable Git/CI adapters.
- A new runtime requires an adapter conformance pack before it can claim verified execution; analysis and plan generation remain available immediately.
- An 8GB laptop is a development/demo target, not the production isolation boundary; untrusted high-impact execution is disabled locally and delegated to the Production Sandbox Worker.