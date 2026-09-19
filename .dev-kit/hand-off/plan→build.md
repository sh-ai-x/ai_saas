# plan → build hand-off

## Plan

- Phase: `admin-pricing-landing-sync`
- Branch/worktree: `plan/admin-pricing-landing-sync`
- Proposal: `/dev-kit:proposal admin-pricing/admin-pricing-landing-sync`
- Goal: make admin pricing writes, PostgreSQL rows, admin rereads, public pricing, and landing props identical.

## Build order

1. `step0`: add the failing regression/integration contract before production changes and record RED evidence.
2. `step1`: fix the smallest observed persistence/projection/cache cause and make the contract green.
3. `step2`: run independent PostgreSQL, full web test, lint, typecheck, build, and code-sanity checks.

## Constraints

- Do not use production credentials or a shared production database.
- Preserve admin authorization, reason/audit requirements, billing-mode validation, and production fail-closed behavior.
- Do not redesign payments, auth, schema, or pricing visuals.

