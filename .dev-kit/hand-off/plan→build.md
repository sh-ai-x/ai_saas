# Plan → Build Handoff — Profile Subscription and Billing Operations

## Baseline

- Phase: `profile-subscription`
- Branch/worktree: `plan/profile-subscription` / `.worktrees/profile-subscription`
- Goal: give end users a trustworthy subscription/token view and give operators a complete per-user billing lifecycle view while keeping Toss provider effects and Neon entitlement state idempotent.
- Evidence: current Neon production has the billing catalog tables but no subscription/order/event rows; the existing subscription schema lacks explicit next-renewal, termination, failure, and event-ordering fields; the Toss adapter has no recurring transition implementation.
- Neon staging check: staging currently has 2 users and 15 payment orders but still 0 subscriptions and 0 billing events, so the build must exercise the new lifecycle with deterministic fixtures before any production rollout.

## Build order

1. `step0`: Neon/Drizzle lifecycle, transition, period snapshot, token limit, and usage ledger schema plus transactional invariants.
2. `step1`: provider-neutral Toss recurring billing, merchant scheduler claim, period-end cancel/resume, renewal/failure/expiry, webhook and reconciliation flow.
3. `step2`: actual token metering, reservation/commit/release, plan-period entitlement projection, and renewal/cancellation quota semantics.
4. `step3`: authenticated profile subscription summary, token usage display, cancel-at-period-end and resume actions.
5. `step4`: admin user subscription directory/detail, audited reconciliation controls, staging rollout, operations, and full lifecycle verification.

## Guardrails

- Cancel means `cancel_at_period_end`; preserve paid access through `current_period_end` and skip the next scheduled Toss billing call. Never remove access immediately from a user request.
- Toss does not schedule recurring payments. The application owns `next_billing_at`, scheduler claims, retries, and reconciliation; every provider call is server-side and idempotent.
- Apply normalized events only after provider proof, order/customer/amount checks, and inbox deduplication. Stale or unknown events are recorded for reconciliation, not allowed to downgrade or grant access blindly.
- Reset token-period usage only after a successful renewal; retain current-period usage through a scheduled cancellation and through the configured payment-failure grace window.
- Keep billing keys and secret references server-only. Browser routes read/use shared server use cases and never write Neon directly.
- Admin reads and mutations require server-side role/scope checks. Mutations require reason and idempotency, capture before/after state, and append an audit event.
- Use Neon staging for migration rehearsal and the repository's preflight/plan/apply/verify process for production. No live payment calls or production writes in the build step.
- The proposal HTML auto-render was not emitted because this checkout does not contain `lib/render_proposal_html.py`; the YAML/HTML renderer can be run when the proposal skill is installed into the repository toolchain.

## Next invocation

Build completed in the `plan/profile-subscription` worktree. Review the diff, run security/review gates, and rehearse the migration/scheduler flow in staging before release.
