Status: pending
Name: pricing-sync-implementation

## Read first

- `PRD.md` §§4–5 and AC-1
- `phases/admin-pricing-landing-sync/step0.md`
- `apps/web/tests/pricing-sync.contract.test.ts`
- `apps/web/lib/pricing/repository.ts`
- `apps/web/app/page.tsx`
- `apps/web/app/api/pricing/route.ts`
- `apps/web/components/admin-pricing-console.tsx`

## Task

Make the smallest production change that turns the failing contract green. Preserve the existing admin authorization, reason requirement, billing-mode validation, audit event, and local fallback behavior. The resulting system must have one authoritative catalog projection for persistence and public rendering.

Investigate the failing evidence before editing. Reconcile child options transactionally when an update payload is authoritative (including removals), ensure the public landing read cannot reuse stale route data after a successful admin mutation, and avoid introducing a second pricing source or client-supplied amount. If the test exposes a different root cause, fix that root cause instead and document it in the step output.

## Acceptance Criteria

- The step0 regression test passes against a real database-backed path and the deterministic contract path.
- An update followed by a fresh admin read, direct database read, public pricing API read, and landing render exposes identical plan/option values.
- Omitted options are deleted or otherwise reconciled according to the request contract, with foreign-key-safe transactional behavior and an audit record.
- Production remains fail-closed when `APP_ENV=production` has no `DATABASE_URL`; local fallback tests remain green.

## Verification & Status Update

Run the focused regression test first, then the relevant repository/API tests. Record commands, exit codes, test counts, and the root cause/fix in `phases/admin-pricing-landing-sync/step1-output.json`.

## Don't

- Do not redesign pricing tables or payment-provider adapters.
- Do not bypass the admin guard, reason validation, or production database requirement.
- Do not fix the symptom by hardcoding landing values or adding a second cache/state store.

