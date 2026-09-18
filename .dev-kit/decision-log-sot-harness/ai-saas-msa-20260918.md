# SOT Harness Decision Log — AI SaaS MSA Foundation

**Session**: `ai-saas-msa-20260918`
**Date**: `2026-09-18`
**Input**: Production-Ready AI SaaS Foundation Template, MSA 방식 설계
**User delegation**: “멀 선택? 알아서 accept” — assistant may select the best recommendation and accept it for each round.

## Round 1 — `project_context`

**Question**: What is the project's primary agent-harness category?

**Choice**: `accept long_running`

**Reason**: The target is a production foundation for AI tasks that can run for minutes or longer and must survive multiple sessions, queue retries, worker restarts, and durable checkpoint handoffs. MSA service boundaries are recorded as a separate runtime architecture overlay.

**Source**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Not selected**:

- `multi_agent_research`: useful for research-specialized workloads, but too narrow for a general AI SaaS foundation.
- `single_agent_coding`: bounded single-window work does not cover the target's long-running production behavior.

## Round 2 — `verification`

**Question**: How will you verify the agent's work?

**Choice**: `accept generator_evaluator_split`

**Reason**: The template spans browser behavior, API contracts, queue semantics, tenant isolation, checkpoint recovery, and billing concurrency. An independent evaluator reduces self-approval bias and can exercise the running system.

**Source**: https://www.anthropic.com/engineering/harness-design-long-running-apps

**Not selected**:

- `self_verification_browser`: retained as a test layer, but not sufficient as the sole verifier.
- `deterministic_only`: retained as mandatory CI gates, but insufficient for semantic cross-service and E2E regressions.

## Round 3 — `context`

**Question**: How will you manage the context window?

**Choice**: `accept filesystem_memory`

**Reason**: Requirements, service contracts, ADRs, progress, evaluator output, and runtime recovery data must survive context resets. Durable artifacts provide the restorable handoff needed by long-running work.

**Source**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Not selected**:

- `frequent_intentional_compaction`: useful optimization, but not a durable source of truth.
- `subagent_firewall`: optional for specialized work and must not hide contract-relevant results.

## Round 4 — `safety`

**Question**: What safety perimeter?

**Choice**: `accept worktree_isolation`

**Reason**: The repository already protects the main checkout with worktree rules. This is the smallest effective safety boundary for documentation and future implementation work, while service-level authorization and secret controls cover runtime risk.

**Source**: https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html

**Not selected**:

- `os_sandbox`: stronger isolation but adds platform and proxy complexity beyond this design-only baseline.
- `contract_of_intent`: research-grade and not required as a production dependency for this template.

## Round 5 — `lifecycle`

**Question**: What session lifecycle?

**Choice**: `accept initializer_progress`

**Reason**: The first session must establish service topology, contracts, feature inventory, local startup, and progress state. Later sessions need a deterministic orientation path and a clean handoff.

**Source**: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

**Not selected**:

- `ralph_loop`: may be layered into the session runner but does not replace the durable project lifecycle.
- `eval_iteration`: belongs to the verification gate and should not be duplicated as lifecycle ownership.

## Validation

- [x] `project_context` locked
- [x] `verification` locked
- [x] `context` locked
- [x] `safety` locked
- [x] `lifecycle` locked
- [x] Every accepted choice has a source URL
- [x] Open questions are present in the hand-off SOT
- [x] Dependency-ordered implementation phases are present

## Result

The interview passes the `sot-harness-writer` acceptance rubric. The hand-off document is:

`.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md`

## Post-interview plan integration

The copied reference SOT set was incorporated into the plan without changing
the five locked harness decisions. The added planning inputs are:

- Google OAuth server-side callback validation and session boundary
- Admin page operations through privileged APIs, typed ledger actions, reasons,
  before/after snapshots, and append-only audit events
- Toss Payments server-side amount/order validation, idempotency, provider
  query verification, billing-key scheduling, and webhook handling
- Lemon Squeezy raw-body signature verification, event allowlisting, status
  mapping, and replay/reconciliation
- A non-production mock adapter that uses the same provider ports, inbox,
  entitlement, ledger, and audit path as real providers

The plan now includes evaluator scenarios, security gates, open questions, and
service ownership for these concerns. No application implementation was added.

## Proposal Gate edit — `mysaas` initial baseline

The proposal was updated after inspecting `../mysaas/my-saas`. It is recorded
as the initial vertical slice of the target foundation, not as a replacement
for the MSA target:

- Initial web/data path: Next.js 16.3, Better Auth, Drizzle, Neon-compatible
  PostgreSQL, Vercel-oriented deployment, Inngest, and Docker local development.
- Existing admin and billing code is treated as migration evidence; its
  super-admin allowlist, provider-specific plan columns, missing Toss adapter,
  missing Lemon webhook route, and non-atomic credit paths are not promoted to
  production contracts without hardening.
- The target retains Vercel/Neon for the first deployable increment and adds
  FastAPI/LangGraph/ECS-Fargate extraction only behind versioned contracts and
  measurable execution/operational thresholds.

No application implementation was added. Ralph remains at the Proposal Gate
awaiting the user's approval of this edited proposal.

## Proposal Gate edit — cost-optimized portfolio profile

The proposal now chooses the lowest-complexity deployable profile as the
default: one Next.js/Vercel web app, one Neon PostgreSQL project, Inngest Hobby
for bounded durable work, Cloudflare basic edge services, mock payments, and
sampled OTel. Toss or Lemon Squeezy is enabled one provider at a time after
the mock path passes.

FastAPI, LangGraph worker extraction, ECS/Fargate, ALB, NAT, Redis/SQS,
per-service databases, and dedicated telemetry are conditional upgrades. Each
upgrade requires a measured workload or isolation trigger, a monthly ceiling,
and a removal/rollback plan. This keeps the portfolio close to free-tier cost
while preserving logical MSA contracts and a credible extraction path.
