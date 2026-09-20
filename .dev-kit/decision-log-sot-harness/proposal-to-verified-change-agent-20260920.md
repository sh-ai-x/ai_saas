# SOT Harness Decision Log

Session: `proposal-to-verified-change-agent-20260920`

## Research basis

All sources were fetched on `2026-09-20`.

| URL | source_type | purpose |
| --- | --- | --- |
| https://docs.langchain.com/oss/python/learn | official documentation | LangChain context engineering and integrations |
| https://langchain-ai.github.io/langgraph/reference/ | official documentation | LangGraph graph orchestration |
| https://langchain-ai.github.io/langgraph/reference/checkpoints/ | official documentation | durable checkpointing |
| https://langchain-ai.github.io/langgraph/concepts/breakpoints/ | official documentation | approval interrupt/resume |
| https://docs.langchain.com/langsmith/evaluation-types | official documentation | offline evaluation datasets and evaluators |
| https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge | official documentation | online evaluation sampling |
| https://www.anthropic.com/engineering/building-effective-agents | primary engineering guidance | bounded workflow selection |
| https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | primary engineering guidance | environment-grounded evaluations |
| https://www.anthropic.com/research/trustworthy-agents | primary research guidance | trustworthy agent controls |
| https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf | government standard guidance | GenAI risk and governance |
| https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy | official documentation | Nginx edge/SSE boundary |
| https://learn.microsoft.com/en-us/azure/architecture/microservices/ | official architecture guidance | bounded service ownership |

## Round 1/5 — project_context

Question: What is the primary agent-harness category?

- A — Proposal-to-Verified-Change Agent: accepted.
  - The workflow is a coding/engineering change-assurance product, not a
    general chat or unrestricted coding agent.
  - Source: https://www.anthropic.com/engineering/building-effective-agents
- B — Document Knowledge Agent: not selected.
  - Generic RAG is an internal retrieval capability, not the product's core
    differentiated outcome.
  - Source: https://docs.langchain.com/oss/python/learn
- C — General Multi-Agent Platform: not selected.
  - A platform-first scope would increase breadth before one user outcome is
    proven.
  - Source: https://langchain-ai.github.io/langgraph/reference/

## Round 2/5 — verification

Question: How will agent work be verified?

- A — Deterministic gates plus LangSmith datasets/evaluators: accepted.
  - Hard facts such as citations, paths, tests, and policy are checked by code;
    quality and regression are measured with versioned evaluation datasets.
  - Source: https://docs.langchain.com/langsmith/evaluation-types
- B — Human approval only: not selected as the sole mechanism.
  - Approval controls side effects but does not provide repeatable quality or
    hallucination measurement.
  - Source: https://langchain-ai.github.io/langgraph/concepts/breakpoints/
- C — LLM-as-a-judge only: not selected as the sole mechanism.
  - Model judges are useful for semantic quality but cannot replace tests,
    authorization, path checks, or security controls.
  - Source: https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge

## Round 3/5 — context

Question: How will context be managed?

- A — Hierarchical context engineering and targeted retrieval: accepted.
  - Requirements, repository maps, and authorized evidence are assembled in
    stages; the full repository is not placed in every prompt.
  - Source: https://docs.langchain.com/oss/python/learn
- B — Full repository in every prompt: not selected.
  - It creates avoidable cost, latency, noise, and sensitive-data exposure.
  - Source: https://docs.langchain.com/oss/python/learn
- C — Autonomous sub-agents and long-term memory from day one: not selected.
  - It increases debugging and evaluation surface before the first workflow is
    reliable.
  - Source: https://langchain-ai.github.io/langgraph/reference/checkpoints/

## Round 4/5 — safety

Question: What safety perimeter is required?

- A — Risk-based approval firewall and sandbox: accepted.
  - Read-only is the default; writes, external calls, and high-impact tools
    require typed policy and approval before execution.
  - Source: https://langchain-ai.github.io/langgraph/concepts/breakpoints/
- B — Fully autonomous execution: not selected.
  - It makes prompt injection and unintended side effects harder to contain.
  - Source: https://www.anthropic.com/research/trustworthy-agents
- C — Plan-only: not selected as the product endpoint.
  - It is safe but does not demonstrate controlled tool use, checkpoint resume,
    sandbox verification, or a complete change package.
  - Source: https://www.anthropic.com/engineering/building-effective-agents

## Round 5/5 — lifecycle

Question: How should execution live across failures and approval waits?

- A — Durable resumable workflow: accepted.
  - LangGraph owns checkpointed graph state and resume; the product run service
    remains the authority for tenant scope, metering, and lifecycle events.
  - Source: https://langchain-ai.github.io/langgraph/reference/
- B — Synchronous request lifecycle: not selected.
  - It cannot reliably support long-running patch/test jobs, approval waits, or
    worker interruption recovery.
  - Source: https://langchain-ai.github.io/langgraph/reference/checkpoints/
- C — Queue-first event-driven MSA from day one: not selected for the MVP.
  - It adds broker and delivery complexity before the bounded workflow and
    evaluation contract are proven.
  - Source: https://learn.microsoft.com/en-us/azure/architecture/microservices/

## Post-interview amendments

The user required explicit measurement of accuracy, hallucination, latency,
safety, AI security, AI ethics, and code sanity. These are locked as release
gates and observability dimensions in the SOT document rather than being left
as qualitative goals. The v1 gates are now explicit: coverage recall >= 0.95,
critical coverage 1.00, evidence precision >= 0.98, unsupported critical claims
0, invalid references 0 for completed packages, ECE <= 0.10, fixture-specific
p95 latency budgets, all required tests passing before `verified`, and zero
tolerance for unauthorized side effects, approval bypass, secret leakage,
cross-tenant access, sandbox escape, disallowed network access, policy false
negatives, and prompt-injection success on the release fixture.

The proposal was tightened to resolve rather than conceal trade-offs. It now
uses capability tiers: every Git repository gets analysis and a plan; a profile
scanner proposes `change-assurance.yaml`; Node/pnpm and Python/pytest are the
first verified adapters; future runtimes use an adapter SDK and conformance
pack; unknown runtimes terminate as `plan_only`; evaluation failures become
sanitized regression candidates in CI; and signed Git/CI adapters can create
branches/PRs or dispatch policy-approved delivery requests with scoped
credentials. Low-risk delivery may be auto-approved by static policy, while
high-impact delivery has one explicit approval interrupt. The corresponding
ADR remains `proposed` until the human proposal gate is approved.

The final review also added two contract-equivalent runtime profiles. Local
Lite targets the user's 8GB MacBook Air with at most two long-lived processes,
SQLite, a filesystem sandbox subprocess, remote/fake model mode, and redacted
LangSmith API traces. Production MSA retains Nginx, PostgreSQL, isolated
Sandbox Worker, and Delivery Adapter boundaries. Local acceptance requires
application peak RSS <= 3GB and no required Docker daemon or local model.

The user also required exact measurability for production use. The normative
metric registry is now `docs/metrics/change-assurance-metrics.md`: every metric
has a formula, event source, numerator/denominator, minimum sample count,
Wilson or bootstrap 95% confidence policy, and release status. The evaluation
ledger is authoritative for `pass`, `fail`, and `insufficient_sample`;
LangSmith remains the redacted trace/evaluator comparison layer.

Project pivotability is also locked. The Agent Platform Kernel owns
product-neutral contracts and controls; `proposal-to-verified-change` is a
replaceable Project Pack resolved through a versioned registry. The kernel
imports ports only, packs cannot write kernel tables directly, and removing the
pack must leave the kernel buildable and health-checkable. See
`docs/architecture/project-pivot-contract.md`.

Token optimization is now a kernel-owned reliability contract rather than a
prompt-level tuning task. `TokenBudgetPort` controls tenant/run/node/context
budgets, model-call and retry limits, provider usage reconciliation, cache
keys, and fail-closed quota behavior. The initial Local Lite profile caps
plan-only runs at 20,000 total model tokens, verification runs at 41,000
maximum including the bounded patch retry, one call at 8,000 input tokens, and
five primary calls plus one bounded patch retry. Deterministic indexing, authorized path/symbol retrieval,
line-preserving limits, content-addressed summaries, and one evidence-triggered
expansion reduce context without sending the full repository.

The metric contract now records exact versus estimated input/output tokens,
model calls, context cache hits, retrieval expansions, budget overruns,
baseline token savings, and quality per 1,000 tokens. The initial savings target
is 30% on identical versioned cases, but the optimization fails if coverage,
grounding, unsupported-claim, critical safety, or test gates regress. The
normative documents are `docs/architecture/token-budget-contract.md` and
`docs/metrics/change-assurance-metrics.md`.
