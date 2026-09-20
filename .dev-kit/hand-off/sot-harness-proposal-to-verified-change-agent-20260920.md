---
doc_id: sot-harness-proposal-to-verified-change-agent
session: proposal-to-verified-change-agent-20260920
status: locked
source_of_truth: contract
last_reviewed: 2026-09-20
---

# SOT Harness — Proposal-to-Verified-Change Agent

## 1. Product decision

The product is a multi-tenant AI engineering change-assurance service. Its
single core promise is:

> Given a proposal or PRD and an authorized repository, produce an
> evidence-backed implementation plan, obtain approval, create a reviewable
> patch in a sandbox, run verification, and return a traceable change package.

This is not a general coding agent, a generic RAG chatbot, an autonomous
deployment system, or a multi-agent swarm. The product solves the gap between
written requirements and a trustworthy code change: requirement coverage,
code-location evidence, controlled side effects, test evidence, and review
history are returned together.

The workflow is deliberately hybrid. Deterministic graph nodes own policy,
permissions, budgets, state transitions, and verification. LLM nodes may
interpret requirements, select read-only tools, propose plans, and draft a
patch, but they never own authorization or completion status.

The v1 operating profile is capability-driven. Every Git repository can receive
inventory, evidence, and a plan. A profile scanner then proposes a validated
`change-assurance.yaml`; built-in Node/pnpm and Python/pytest adapters support
verified execution, while unknown runtimes safely remain `plan_only`. A signed
Git/CI delivery adapter can create a branch/PR and dispatch a policy-approved
delivery request with scoped credentials. Repository context uses a bounded
inventory and path/symbol index rather than a vector database. One model
provider is selected per deployment with no silent fallback.

Two runtime profiles implement the same contracts. Local Lite targets an 8GB
MacBook Air: at most two long-lived processes, SQLite checkpoints, filesystem
sandbox subprocesses, remote model or fake provider, redacted LangSmith traces,
and no Docker Desktop/PostgreSQL/Redis/Kafka/vector database/Nginx requirement.
Production MSA uses separate Nginx, API, orchestrator, sandbox, delivery, and
PostgreSQL boundaries. Local Lite is a resource-bounded development profile,
not the production isolation boundary.

Source: [Anthropic — Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)

### Research evidence ledger

The following sources were reviewed during the 2026-09-20 research pass. The
`source_type` field distinguishes vendor documentation, primary engineering
guidance, and standards guidance.

| source | fetched_at | source_type | design claim supported |
| --- | --- | --- | --- |
| https://docs.langchain.com/oss/python/learn | 2026-09-20 | official documentation | LangChain context engineering and typed integrations |
| https://langchain-ai.github.io/langgraph/reference/ | 2026-09-20 | official documentation | explicit graph orchestration and durable execution |
| https://langchain-ai.github.io/langgraph/reference/checkpoints/ | 2026-09-20 | official documentation | checkpoint persistence and resumability |
| https://langchain-ai.github.io/langgraph/concepts/breakpoints/ | 2026-09-20 | official documentation | approval interrupt/resume |
| https://docs.langchain.com/langsmith/evaluation-types | 2026-09-20 | official documentation | offline evaluation datasets and evaluator types |
| https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge | 2026-09-20 | official documentation | sampled online quality monitoring |
| https://www.anthropic.com/engineering/building-effective-agents | 2026-09-20 | primary engineering guidance | prefer bounded workflows and simple composition |
| https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | 2026-09-20 | primary engineering guidance | environment-grounded agent evaluation |
| https://www.anthropic.com/research/trustworthy-agents | 2026-09-20 | primary research guidance | human control, transparency, privacy, and security |
| https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf | 2026-09-20 | government standard guidance | GenAI risk, safety, security, and governance |
| https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy | 2026-09-20 | official documentation | edge routing and streaming proxy boundary |
| https://learn.microsoft.com/en-us/azure/architecture/microservices/ | 2026-09-20 | official architecture guidance | bounded contexts and ownership-based service boundaries |

## 2. Harness dimensions and locked decisions

### 2.1 Project context — accepted A

Primary category: coding/engineering execution agent.

The first vertical slice is `proposal -> repository analysis -> evidence-backed
plan -> approval -> sandbox patch -> tests -> report`. The product is sold as
change assurance and reviewability, not as an unrestricted replacement for a
developer.

Rationale: well-defined work should use predictable workflows; agentic choice
is reserved for interpretation, retrieval, and bounded tool selection.

Source: [Anthropic — Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)

### 2.2 Verification — accepted A, strengthened

Verification uses two independent layers:

1. Deterministic gates for requirement schema validity, citation resolution,
   allowed-path enforcement, patch format, test results, secret scanning,
   policy checks, and output schema validity.
2. LangSmith offline datasets and regression evaluations for plan quality,
   requirement coverage, evidence grounding, hallucination, tool selection,
   safety behavior, and model/prompt changes. Sampled online evaluators may
   monitor production runs after redaction.

The system must not mark a run successful because a model returned text. A run
is successful only when its evidence bundle satisfies all required gates.

Source: [LangSmith — Evaluation Types](https://docs.langchain.com/langsmith/evaluation-types)
Source: [Anthropic — Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### 2.3 Context — accepted A, strengthened

Use hierarchical context engineering:

1. Parse the proposal into typed requirements and acceptance criteria.
2. Build a repository inventory and bounded repository map.
3. Retrieve only authorized files, symbols, tests, and configuration relevant
   to the current requirement.
4. Preserve source paths, line ranges, hashes, and retrieval reasons in the
   evidence state.
5. Keep LangGraph short-term graph state separate from product records and
   the manifest-backed repository inventory. V1 uses a path/symbol index and
   does not introduce a vector database.

The full repository is never placed in one prompt by default. Retrieved source
is untrusted data, not instructions that can expand tool permissions.

Token use is bounded by the kernel `TokenBudgetPort`, not by a prompt-side
guess. The context pipeline deterministically indexes the repository, selects
authorized paths and symbols, preserves line ranges under a token limit,
reuses content-addressed summaries, and expands retrieval at most once when a
coverage or schema check proves it necessary. The initial Local Lite profile
caps plan-only runs at `20,000` total model tokens, verification runs at
`41,000` maximum including the bounded patch retry, and one model call at
`8,000` input tokens. A budget exhaustion
produces `quota_paused` or `budget_exceeded`; it never silently truncates
evidence or grants `verified`.

Source: [LangChain — Learn / Context Engineering](https://docs.langchain.com/oss/python/learn)
Source: [LangGraph — Checkpointing](https://langchain-ai.github.io/langgraph/reference/checkpoints/)
Source: [Repository SOT — Memory and Retrieval](../../docs/sot/agent/memory-and-retrieval.md)

### 2.4 Safety — accepted A, strengthened

Use a risk-based approval firewall and sandbox:

- read-only repository inspection is the default;
- file writes, branch creation, patch application, test execution with side
  effects, external requests, issue creation, and merge/deploy actions have
  explicit tool policies;
- patch application and tests run only in an isolated, bounded workspace;
- LangGraph `interrupt()` pauses before high-impact actions and persists the
  state needed for resume;
- tool calls carry tenant, project, run, path, idempotency, timeout, retry,
  redaction, and approval metadata;
- the manifest is validated before patching or execution and supplies the
  allowed paths, test command, resource limits, and retention profile;
- external network access is denied by default and allowlisted per tool;
- no arbitrary shell tool or model-generated network destination is available;
- secrets, credentials, raw prompts, and unredacted source are excluded from
  LangSmith traces by default.

Prompt-injected repository content must never be treated as a policy or tool
authorization source.

Source: [LangGraph — Interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)
Source: [Anthropic — Trustworthy Agents in Practice](https://www.anthropic.com/research/trustworthy-agents)
Source: [NIST — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)

### 2.5 Lifecycle — accepted A, strengthened

Use a durable, resumable workflow exposed through Nginx SSE:

```text
created
  -> inventorying
  -> analyzing
  -> planning
  -> waiting_approval
  -> patching
  -> testing
  -> evaluating
  -> completed | failed | cancelled | quota_paused | plan_only
completed -> delivery_requested -> delivery_ready | delivery_failed
```

Each transition is server-controlled and append-only. LangGraph checkpoint
state is mapped to the product `run_id`; the two identifiers must not create
two competing lifecycle authorities. Retry is idempotent by node and tool
identity. The browser receives progress but never calls the worker directly.

Source: [LangGraph Reference](https://langchain-ai.github.io/langgraph/reference/)
Source: [LangGraph — Checkpointing](https://langchain-ai.github.io/langgraph/reference/checkpoints/)

## 3. Three-framework layer contract

### LangChain — intelligence and integration layer

LangChain owns model adapters, prompt templates, output schemas, retrievers,
and typed tools. It must not own tenant authorization, billing, run state, or
the final success decision. Model output is parsed into typed domain objects
before it can change state.

Required LangChain components:

- one configured provider implementation behind a small provider-neutral model
  boundary; no silent provider fallback in v1;
- `Requirement`, `EvidenceRef`, `ImplementationPlan`, `PatchProposal`, and
  `VerificationReport` structured schemas;
- manifest-backed repository inventory and targeted path/symbol retrieval tools;
- tool descriptions with explicit read/write/network/approval metadata;
- no arbitrary shell tool exposed to the model.

### LangGraph — orchestration and state layer

LangGraph owns the workflow graph, conditional routing, checkpointing,
interrupt/resume, bounded retry, and state transition events. The graph is
explicit rather than an unconstrained loop.

Initial nodes:

`intake -> profile_validate -> inventory -> retrieve -> analyze -> plan ->
human_approval -> patch -> test -> evaluate -> report -> delivery_policy ->
delivery_adapter`

If `profile_validate` fails, the graph ends in `plan_only` after producing an
evidence-backed plan. It does not attempt a patch or test command.

Delivery is optional. A verified package can be handed to a signed Git/CI
adapter; delivery failure never changes the verification result. Static policy
may auto-approve low-risk delivery, while high-impact delivery uses one
explicit approval interrupt.

The graph has hard limits for wall-clock duration, node attempts, model calls,
retrieved bytes, changed files, test duration, and total usage units.

The kernel also enforces token budgets, provider usage reconciliation, context
cache keys, and cost ceilings. Project Packs can supply prompts and retrieval
hints but cannot increase those limits. Deterministic schema, path, and test
failures do not spend another model call; a bounded retry receives the failure
code, missing evidence IDs, and compact repair context rather than the full
transcript.

### LangSmith — evidence and evaluation layer

LangSmith receives redacted traces for model calls, graph nodes, tool calls,
retrieval references, latency, token usage, errors, evaluator scores, and
version metadata. It is not the authorization source, product database, or
billing ledger.

Required datasets/evaluators:

- `plan-coverage`: requirements mapped to plan steps;
- `evidence-grounding`: every claim resolves to an existing authorized path
  and line range;
- `hallucination`: unsupported claims divided by factual claims;
- `patch-verification`: tests and acceptance checks pass;
- `tool-safety`: blocked actions remain blocked and approvals are respected;
- `latency-cost`: node and end-to-end p50/p95 latency and usage units;
- `security-redteam`: prompt injection, path traversal, command injection,
  secret exposure, poisoned repository content, and cross-tenant access.

Evaluation is code-owned. Failed cases are sanitized into regression
candidates, reviewed by policy, versioned, and replayed in CI. LangSmith is
the trace/evaluation surface for redacted metadata, not a separate manual
maintenance process or an authority source.

## 4. Reliability and quality metrics

Every completed run emits a machine-readable evaluation report. Thresholds are
configuration, not hidden prompt instructions.

### Accuracy and grounding

- `requirement_coverage_recall`: requirements with a valid plan mapping / all
  parsed requirements;
- `evidence_precision`: valid authorized evidence references / all emitted
  evidence references;
- `acceptance_criteria_coverage`: acceptance criteria represented in the plan
  and verification commands / all acceptance criteria;
- `patch_test_pass_rate`: runs whose required tests pass / patch attempts;
- `human_accept_rate`: approved change packages / reviewed change packages.
- `delivery_request_success_rate`: provider-acknowledged delivery requests /
  policy-approved delivery requests; this never rewrites verification status.

### Hallucination

- `unsupported_claim_rate`: factual claims without a valid evidence reference
  / all factual claims in the plan and report;
- `invalid_reference_rate`: missing, inaccessible, or mismatched file/line
  references / all emitted references;
- `uncertainty_calibration`: agreement between declared confidence buckets and
  evaluator-confirmed correctness.

The product must show “insufficient evidence” rather than inventing a file,
requirement, test result, or completion state.

### v1 release gates

These are the initial release-blocking targets for the supported fixture class.
They are measured on a versioned gold dataset containing normal, ambiguous,
incomplete, and adversarial proposals. A baseline may be reported separately,
but a baseline cannot waive a failed release gate.

- `requirement_coverage_recall >= 0.95`, with `1.00` for requirements marked
  critical by the fixture;
- `acceptance_criteria_coverage >= 0.95` and `evidence_precision >= 0.98`,
  with `1.00` for critical claims and references;
- `unsupported_claim_rate <= 0.02` overall and `0` for critical claims;
- `invalid_reference_rate = 0` for any run allowed to produce a completed
  change package;
- all required tests and acceptance checks pass before a package can be
  labelled `verified`; a failing check produces `failed` or `needs_review`;
- `uncertainty_calibration` is reported for every evaluation batch, with
  expected calibration error `<= 0.10` as the initial target;
- p95 latency is measured against the small-repository release fixture:
  `<= 120s` for plan-only runs and `<= 600s` for patch-plus-test runs;
- unauthorized side effects, approval bypass, secret leakage, cross-tenant
  access, sandbox escape, disallowed network access, and high-impact policy
  false negatives are all `0`;
- prompt-injection attack success is `0` on the release red-team fixture;
- the release report includes sample count, confidence interval or exact
  denominator, evaluator version, model/prompt version, and every failed case.

Metrics are never averaged across incompatible repository sizes or workflow
statuses. A denominator of zero is reported as `not_applicable`, not as a
perfect score. Human acceptance remains a monitored product signal rather than
a sole safety or correctness gate.

The authoritative formula, event vocabulary, sample minimums, Wilson/bootstrap
confidence policy, and release report schema are defined in
[Change-Assurance Metrics Contract](../../docs/metrics/change-assurance-metrics.md).
The product evaluation ledger owns release status; LangSmith owns redacted
trace and evaluator comparison data.
The token-specific budgets, cache key, retry rules, and hard-stop contract are
defined in [Token Budget Contract](../../docs/architecture/token-budget-contract.md).

### Latency and cost

- end-to-end p50/p95 from run creation to report;
- per-node p50/p95 for retrieval, planning, patching, testing, and evaluation;
- model calls, input/output tokens, context tokens, cache hits, retrieval
  expansions, usage units, and cost per run;
- budget overrun rate, token savings against a fixed baseline, and quality per
  1,000 tokens;
- queue delay and sandbox startup time;
- retry rate and checkpoint resume time.

Local Lite adds resource metrics: application peak RSS, long-lived process count,
Docker daemon state, local model process state, and swap pressure. Its release
gate is application peak RSS `<= 3GB`, at most two long-lived application
processes, no required Docker daemon, and no required local model process.
Production resource SLOs are measured separately and never substituted for the
laptop gate.

### Safety and security

- unauthorized side effects: target `0`;
- approval bypass rate: target `0`;
- secret leakage in output/trace: target `0`;
- cross-tenant evidence access: target `0`;
- sandbox escape and disallowed network requests: target `0`;
- prompt-injection attack success rate: target `0` on the release fixture;
- policy-denial false negative rate: target `0` for high-impact tools.

Security checks combine deterministic tests, adversarial fixtures, dependency
scanning, secret scanning, and independent review. AI ethics checks require
clear agent identity, user-visible uncertainty, user control over side
effects, data minimization, retention/deletion behavior, and no fabricated
confidence or hidden action.

Sources: [NIST AI Resource Center](https://airc.nist.gov/)
Source: [Anthropic — Trustworthy Agents in Practice](https://www.anthropic.com/research/trustworthy-agents)

## 5. Code sanity contract

- Control API, orchestrator, sandbox, and web have explicit ownership.
- Nginx contains routing and transport policy only; no business logic.
- Services communicate through versioned REST/events; no direct cross-service
  table writes.
- Authorization and metering remain server-owned.
- LangChain schemas are validated at every model boundary.
- LangGraph state is typed and serializable.
- Tools are registered explicitly; dynamic import or arbitrary command
  construction is prohibited.
- Profile and delivery adapters implement versioned capability schemas and pass
  conformance tests before activation.
- The kernel imports ports only; it cannot import `project-packs/*`, and packs
  cannot write kernel tables directly or import other packs.
- Delivery requests use scoped, short-lived credentials and signed payloads;
  the orchestrator never receives ambient merge or deploy authority.
- Local Lite and Production MSA implement the same versioned contracts; local
process co-location is a deployment profile, not a boundary change.

The reusable Agent Platform Kernel is separated from the
`proposal-to-verified-change` Project Pack. The kernel owns product-neutral
contracts, policy, run/checkpoint state, approval, metering, audit, sandbox
protocol, evaluation ledger, metrics, and runtime profiles. The Project Pack
owns prompts, requirement extensions, retrieval ranking, tools, adapters,
report copy, and datasets. The kernel never imports a Project Pack; packs are
resolved through a versioned registry and must pass conformance tests. The
normative pivot rules are in
[Project Pivot Contract](../../docs/architecture/project-pivot-contract.md).
- Every run emits append-only, monotonic events for profile detection,
  requirements, evidence, tools, approvals, patch/test, evaluation, report,
  delivery, cancellation, resume, model usage, token budget decisions, context
  cache hits/misses, and retrieval expansion; retries add attempts under the
  same idempotency key.
- Each step has unit, contract, integration, evaluation, security, and browser
  verification where applicable.
- A build step is not complete from subprocess exit code alone; its declared
  verification must run and produce evidence.
- Full typecheck, lint, tests, dependency audit, secret scan, and intent
  integrity checks are required before completion.

## 6. Runtime profiles and minimum deployment architecture

### Local Lite — 8GB MacBook Air

- two long-lived processes maximum: web/control API and orchestrator;
- sandbox runs as a bounded subprocess against a temporary workspace;
- SQLite owns local run/checkpoint/audit state;
- filesystem path/symbol index replaces vector infrastructure;
- remote model API with allowlisted/redacted context or deterministic fake
  provider; no local model server;
- redacted LangSmith API traces; no local telemetry collector;
- no Docker Desktop, PostgreSQL, Redis, Kafka, vector database, or Nginx
  requirement.

Untrusted high-impact execution is disabled in Local Lite and delegated to the
Production Sandbox Worker. The local profile is accepted only when application
peak RSS is `<= 3GB`, long-lived application process count is `<= 2`, and no
required Docker daemon, local model process, or swap-inducing service is active.

### Production MSA

```text
                 public HTTPS / SSE
                        |
                      Nginx
          _____________|________________
         |             |                |
     Web Console   Control API   Agent Orchestrator
                       |                |
                 PostgreSQL       LangGraph
                       |                |
                  Metering       Sandbox Worker
                                      |
                              isolated workspace
                                       |
                            Signed Git/CI Adapter
```

The first deployment uses Docker Compose or an equivalent small container
deployment. It does not introduce Kubernetes, Kafka, a service mesh, or
separate physical databases. PostgreSQL remains one deployment with schema
ownership boundaries until scale or isolation evidence justifies extraction.

Nginx is used for TLS termination, route proxying, request limits, and SSE
transport. Streaming locations disable proxy buffering and set bounded read
timeouts. The product API remains the authority for auth, tenant scope, run
state, and usage.

Source: [NGINX Reverse Proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy)
Source: [Microsoft — Microservices Architecture](https://learn.microsoft.com/en-us/azure/architecture/microservices/)

## 7. Product boundaries

In scope for the first release:

- one repository per project;
- one proposal/PRD per run;
- inventory and plan generation for every Git repository;
- an auto-generated, user-confirmed `change-assurance.yaml` capability manifest;
- Node/pnpm and Python/pytest execution adapters;
- adapter SDK and conformance test pack for future runtimes;
- read-only inspection, approved patching, and sandbox verification;
- signed Git branch/PR creation and policy-gated CI delivery through scoped
  provider adapters;
- Local Lite runtime acceptance on an 8GB MacBook Air;
- Production MSA deployment profile with separately deployable boundaries;
- Agent Platform Kernel plus replaceable Project Pack registry;
- one authenticated tenant boundary;
- usage metering and audit history;
- one configured model provider per deployment;
- path/symbol retrieval without a vector database;
- kernel-owned token budgets, context caching, bounded retrieval expansion,
  usage reconciliation, and fail-closed quota behavior;
- LangSmith tracing and evaluation-as-code with automatic sanitized regression
  candidates.

Out of scope:

- arbitrary internet browsing or external API actions;
- autonomous credential handling;
- multi-agent delegation;
- arbitrary shell commands, vector database infrastructure, provider fallback,
  ambient credentials, and model-generated network destinations;
- local LLM serving and always-on local infrastructure services in Local Lite;
- public repository creation or automatic push.

The product repository may be a new private repository derived from the
foundation, but repository creation, remote configuration, and push are a
separate explicitly authorized delivery step after proposal and plan review.

## 8. Implementation phases

1. **Kernel and Project Pack contracts** — product-neutral schemas, ports,
   profile/manifest and delivery contracts, run/evidence/report contracts,
   registry rules, initial gold dataset, metric registry/event vocabulary,
   confidence policy, token budget/cache/usage ports, and failure fixtures.
2. **Repository context service** — inventory, bounded retrieval, authorization,
   auto-profile generation, evidence references, token-aware context selection,
   and prompt-injection fixtures.
3. **LangChain intelligence layer** — selected provider adapter, structured
   outputs, path/symbol retrievers, typed read-only tools, redaction, and
   provider tests.
4. **LangGraph orchestrator** — typed state graph, checkpoint persistence,
   approval interrupts, idempotent retry, cancellation, and SSE events.
5. **Sandbox worker** — isolated patch/test execution, path/network policy,
   test evidence, timeout, cleanup, and interruption recovery.
6. **LangSmith observability and evaluation** — redacted trace mapping,
   evaluation-as-code, sanitized failure candidates, offline regression suite,
   online sampling, latency/cost/token dashboards, and evaluator thresholds.
7. **Delivery adapters** — scoped Git/CI provider ports, signed PR creation,
   policy-gated dispatch, low-risk auto-approval, high-risk interrupt, and
   delivery failure recovery.
8. **Runtime profiles and minimal MSA deployment** — Local Lite two-process
   profile with SQLite and 8GB memory checks, Production MSA container
   boundaries, Nginx proxy/SSE configuration, health/readiness checks, and
   contract-equivalence tests.
9. **Hardening and packaging** — code sanity, AI security, ethics review,
   browser verification, private-repository packaging, and hand-off evidence.

## 9. Open questions

- Is the repository supplied as a local upload, Git provider connection, or
  both?
- What sandbox runtime is available for the target private deployment?
- Will the new private repository remain portfolio-private, or will a public
  demo/specification repository be published later?
