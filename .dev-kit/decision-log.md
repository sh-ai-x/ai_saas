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

# frame — jev-faq-provider-restore

- goal: Restore the archived Jev FAQ provider behind the existing FaqProvider port as a config-flagged alternative to OpenAI, fix the two bugs a verbatim revert would re-ship, document why OpenAI was chosen, and document the environment variables.
- target_user: The repository maintainer/operator who cannot currently tell from any file why the FAQ bot routes through OpenAI, and has no config path back to Jev.
- situation: A customer-facing FAQ bot is merged; Jev was its original provider, deleted and replaced by OpenAI with no rationale recorded anywhere in the repo.

# interview — jev-faq-provider-restore

- status: SKIPPED
- reason: The design was already fully settled through iterative review of `docs/proposals/reviewing/jev-typesafe-integration/idea-jev-typesafe-integration.yaml` directly with the maintainer across multiple rounds (draft, cheapest-slice trim, cons/limitations resolution, third-bug documentation) before this plan stage began. No open design question remained.

# gate-2 cycle 1 — jev-faq-provider-restore

- evidence: 3 independent signals (git history, source code, maintainer statement) recorded in PRD §2.
- value: engineering cost avoided, $600 (3 avoided recurrences of the archaeological recovery at $200 each) / cost $100 = value_score 6.0.
- ambiguity: 10 → 6 → 3 → 2; narrowed by identifying the FAQ router as the concrete integration point, then by the proposal's own iterative scope trim (cheapest-slice, cons/limitations resolution, third-bug fold-in).
- next: implement step1 (env var docs + one-time live wire-contract check) — step0 was already implemented and verified before this plan stage began.

# gate-3 — jev-faq-provider-restore

- non_goals: removing/deprecating the OpenAI adapter; retuning confidence/answerable thresholds; the widget ranking cap and email-escalation gap (deferred, separate proposals); a provider-factory abstraction module.
- breach_response: reject scope changes that would remove OpenAI or retune thresholds without real Jev traffic data; defer ranking/escalation and factory-module requests to their own proposals.
