# frame

- goal: Make an admin pricing edit persist to the PostgreSQL pricing tables and become the exact catalog shown by the public landing page on the next read.
- target_user: A SaaS product administrator maintaining plans and prices from `/admin/pricing`.
- situation: The administrator can save a pricing value, but the admin view, database rows, public pricing API, and landing page can show different catalogs.

# interview

- status: SKIPPED
- reason: The user supplied an explicit implementation scope and required order (`dev-kit:plan -> dev-kit:build`); no separate interview hand-off was available in this worktree.

# gate-2 cycle 1

- evidence: 3 independent repository/runtime/user signals recorded in PRD §2.
- LTV: $240 × 25 users = $6,000 / cost $1,200 = value_score 5.0.
- ambiguity: 10 → 7 → 5 → 3; narrowed by tracing admin write, PostgreSQL projection, public API, and landing render paths.
- next: build a red-first database-to-landing consistency contract.

# gate-3

- non_goals: schema redesign; payment-provider changes; authorization redesign; visual pricing redesign.
- breach_response: defer each request to a separate scoped plan and keep this change limited to catalog consistency.

# frame — jev-cs-faq-bot

- goal: Ship a bottom-right FAQ Support bot that answers catalog-backed questions deterministically and uses JEV only as a bounded category/FAQ router when fixed matching misses.
- target_user: A product user trying to resolve a common setup, login, pricing, or agent-run question without opening a support request.
- situation: The application has a Drizzle FAQ table and seed data but no API, JEV decision path, or visible FAQ surface, so users cannot discover or use the catalog.

# interview — jev-cs-faq-bot

- status: SKIPPED
- reason: The user supplied explicit implementation scope and the JEV SOT/proposal artifacts already record the safety, provider, cost, latency, and fallback decisions.

# gate-2 cycle 1 — jev-cs-faq-bot

- evidence: 4 independent repository/provider/workflow/privacy signals recorded in PRD §2.
- LTV: 240 value units × 25 users = 6,000 / cost 1,200 = value_score 5.0.
- ambiguity: 10 → 7 → 5 → 3; narrowed by fixing the catalog-owned answer boundary, one-call JEV routing, and deterministic fallback contract.
- next: implement the single vertical slice and verify the live-provider gate separately.

# gate-3 — jev-cs-faq-bot

- non_goals: open-ended generation; account/billing/ticket mutations; RAG/memory/tools/attachments; live-provider dependency in local/test.
- breach_response: defer each request to a separate security/evaluation plan and keep this phase read-only, bounded, and catalog-backed.

# frame — ai-change-impact-review

- goal: Build a low-token, read-only workbench that compares a local HTML/PDF proposal with a local Git repository and returns requirement-level code evidence, impact, risks, and a human-reviewed ready/revise/blocked decision.
- target_user: An AI Engineer evaluating prompt, model, retriever, graph, or provider changes before implementation.
- situation: The engineer currently reads the proposal, searches the repository, infers affected modules, and judges feasibility manually, while whole-repository LLM/JEV analysis is expensive and difficult to reproduce.

# interview — ai-change-impact-review

- status: SKIPPED
- reason: The user supplied the product decision, low-token constraint, local-only boundary, and explicit plan/build request.

# gate-2 cycle 1 — ai-change-impact-review

- evidence: 6 independent repository/PDF/product signals recorded in PRD §2.
- LTV: 240 value units × 25 users = 6,000 / cost 1,200 = value_score 5.0.
- ambiguity: 10 → 8 → 6 → 4 → 3; narrowed by fixing local parsing, Git exclusion, deterministic evidence retrieval, one-call synthesis, and no-code-execution scope.
- next: implement the deterministic local context boundary before provider-backed synthesis.

# gate-3 — ai-change-impact-review

- non_goals: full repository upload; code/build/test/deploy execution; file-by-file LLM/JEV judging; baseline/candidate bulk experiments.
- breach_response: create a separate scoped phase and preserve the low-token read-only review contract.
