# Proposal-to-Verified-Change Agent plan decision log

## frame

- goal: Ship a bounded AI agent that turns an approved proposal and an authorized Git repository into an evidence-backed, sandbox-verified change package with measurable token, quality, safety, and cost behavior.
- target user: A senior engineer or technical founder maintaining a small-to-medium repository without a dedicated AI platform team.
- situation: The user can ask an LLM for a plan or patch, but cannot reliably prove that requirements were covered, repository evidence was valid, tests were run, secrets were protected, or token spend stayed within a safe budget.

## gate-2 cycle 1

- evidence: 3 independent signals accepted from the foundation boundary, official Lang* role separation, and the normative metrics contract.
- LTV: 800 value units × 10 reachable users = 8,000 / cost 2,000 = value_score 4.0.
- ambiguity: 10 → 2 after locking the single workflow, capability tiers, runtime profiles, pivot boundary, and fail-closed safety/token rules.
- next: emit the approved phase plan.

## approval

- proposal: `docs/proposals/applied/proposal-to-verified-change-agent/idea-proposal-to-verified-change-agent.yaml`
- status: accepted
- approved_at: 2026-09-21
- implementation phase: `proposal-to-verified-change`
- build branch base: `plan/proposal-to-verified-change-agent`
- legacy foundation/pricing plan artifacts removed from this product branch.

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