Status: pending
Name: pricing-sync-failing-contracts

## Read first

- `PRD.md` §§1–5, especially AC-0
- `apps/web/lib/pricing/repository.ts`
- `apps/web/app/api/admin/pricing/route.ts`
- `apps/web/app/api/admin/pricing/[id]/route.ts`
- `apps/web/app/api/pricing/route.ts`
- `apps/web/app/page.tsx`
- `apps/web/tests/api-contract.test.ts`
- `apps/web/tests/pricing-repository.test.ts`
- `apps/web/db/schema/pricing.ts`

## Task

Write the regression tests before changing production code. Reproduce the complete invariant across the administrator mutation, actual PostgreSQL rows, admin reread, public pricing API, and landing-page data. Include a deterministic contract test for child-option replacement/removal and a real-PostgreSQL integration path that is explicit about its database prerequisite and cannot silently fall back to the in-memory seed.

The first execution must demonstrate RED against the current implementation. Keep the test assertions focused on observable contracts: the edited plan and options must be equal across every read surface, omitted options must not remain in the database/public catalog, and the active billing projection must be the same one rendered by the landing page.

## Acceptance Criteria

- `apps/web/tests/pricing-sync.contract.test.ts` exists and exercises admin update → database read → admin/public/landing read comparison.
- The test covers an update that changes a value and omits an existing child option, so a stale database child cannot be hidden by a shallow plan assertion.
- The database-backed test is opt-in or uses a dedicated test database, fails closed when its prerequisite is missing, and never changes production data.
- The red-first command and its non-zero result are recorded in `phases/admin-pricing-landing-sync/step0-output.json`.

## Verification & Status Update

Run the focused web test from `apps/web` and record the exact command, exit code, failure assertion, and test count. Do not modify production code in this step. Leave the phase step pending until the failing test is reviewable.

## Don't

- Do not change repository, API, landing, schema, or Docker production code in this step.
- Do not delete or weaken existing pricing tests.
- Do not use a production `DATABASE_URL` or commit credentials.

