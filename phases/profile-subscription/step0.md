# step0.md

## Status

completed

## Read first

- `PRD.md` §2 lifecycle decisions and Neon review
- `apps/web/db/schema/pricing.ts`
- `apps/web/db/schema/auth.ts`
- `apps/web/drizzle/0000_loud_salo.sql`
- `scripts/migration-preflight.mjs`
- `.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md`

## Task

Design and implement the Neon/Drizzle persistence contract for subscription lifecycle and token entitlements. Add additive migration(s) for explicit internal/provider states, cancellation and renewal timestamps, grace/failure metadata, transition history, provider-event processing/order fields, plan token dimensions/version, subscription-period snapshots, and append-only token usage. Define the transactional invariants before any provider or UI work: one active/pending paid subscription per user/tenant, a period-end cancellation preserves access until the end timestamp, a successful renewal creates the next period snapshot exactly once, and every event/usage effect has an idempotency key. Preserve the existing mock/one-time catalog and make the migration safe for current Neon rows.

## Acceptance Criteria

1. The staging migration applies cleanly against the current schema and existing rows; the schema exposes the lifecycle, transition, period, and usage fields needed by the profile, scheduler, and admin queries.
2. Database/domain contract tests prove the active-subscription invariant, append-only transition/usage history, provider-event uniqueness, period snapshot immutability, and safe cancellation/renewal timestamps.
3. The migration plan identifies indexes for profile reads, scheduler claims, admin filters, and period usage aggregation and does not expose or persist a raw billing key in a browser-facing record.

## Verification & Status Update

```bash
pnpm --dir apps/web db:verify:stage -- --from-file .env.staging
pnpm --dir apps/web test -- --runInBand db pricing migration subscription
pnpm --dir apps/web typecheck
```

## Don't

- Do not apply a migration to production from a development step.
- Do not delete or rewrite existing pricing/order/subscription history.
- Do not store a raw Toss billing key in a public response, client state, or log.
