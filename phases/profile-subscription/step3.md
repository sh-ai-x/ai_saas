# step3.md

## Status

completed

## Read first

- `PRD.md` §4 Step 3 and §5 acceptance criteria
- `apps/web/app/billing/page.tsx`
- `apps/web/app/app/page.tsx`
- `apps/web/app/admin/layout.tsx`
- `apps/web/lib/auth/session.ts`
- `apps/web/lib/admin-guard.ts`
- `apps/web/components/billing-catalog-page.tsx`
- `apps/web/components/session-control.tsx`

## Task

Add an authenticated profile/billing page and server routes backed by one subscription-summary use case. The page must show the current plan name and normalized status, paid-through/current period dates, next automatic billing date, scheduled cancellation date when present, failed-payment/grace messaging, token limit/used/remaining progress, and a concise event/history view. Add confirmable actions for cancel-at-period-end and resume-before-period-end with idempotency and clear loading/error states. Keep entitlement checks on the server; do not trust query parameters, payment redirects, or client-computed dates.

## Acceptance Criteria

1. An authenticated user sees a consistent server-owned subscription and token summary, including plan status, paid-through date, next billing date, scheduled cancellation date, and current/limit/remaining tokens.
2. Cancel schedules the subscription at the current period end without removing paid access, and resume clears the schedule only before the period end; repeated requests are safe and visibly reflected.
3. Pending, active, cancel-scheduled, past-due/grace, expired, and provider-sync-pending states have distinct accessible copy and do not reveal payment credentials or another user's data.

## Verification & Status Update

```bash
pnpm --dir apps/web test -- --runInBand profile billing subscription
pnpm --dir apps/web lint
pnpm --dir apps/web typecheck
```

## Don't

- Do not add direct browser writes to Neon or provider APIs.
- Do not promise immediate cancellation when the provider charge is only skipped at the next billing boundary.
- Do not show another user's subscription or usage through an unscoped query.
