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

