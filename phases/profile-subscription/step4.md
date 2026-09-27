# step4.md

## Status

completed

## Read first

- `PRD.md` §3 non-goals and §5 acceptance criteria
- `apps/web/app/admin/page.tsx`
- `apps/web/app/admin/payments/page.tsx`
- `apps/web/components/admin-operations-console.tsx`
- `apps/web/lib/admin-guard.ts`
- `services/admin_operations/service.py`
- `tests/test_identity_tenant_admin.py`
- `tests/test_integration_contracts.py`

## Task

Add an authorized admin subscription directory/detail surface. Operators must be able to search/filter users by plan, normalized status, provider, cancellation schedule, next billing date, grace/failure state, and token usage, then inspect the transition/event/reconciliation history. Keep mutations narrow: any cancel/resume/reconcile/repair action must use the shared billing use case, require operator reason and idempotency, check role/resource scope, capture before/after snapshots, and append an audit event. Add staging migration rehearsal, scheduler health/reconciliation checks, provider replay fixtures, operational copy, and a final verification matrix for the full lifecycle.

## Acceptance Criteria

1. An authorized admin can view every user’s plan/status, current period, next billing date, cancellation date, payment failure/grace state, and token limit/usage with pagination and safe tenant/user scoping.
2. Every privileged mutation and reconciliation records actor, reason, idempotency key, before/after state, provider event/reference, and result; unauthorized or cross-tenant access is denied.
3. Staging migration verification, duplicate/out-of-order/failure/renewal/cancellation fixtures, scheduler recovery, profile/admin UI checks, and focused web/Python suites pass with no production writes or live payment calls.

## Verification & Status Update

```bash
pnpm --dir apps/web test -- --runInBand admin subscription billing
pnpm --dir apps/web lint
uv run --locked python -m unittest tests/test_identity_tenant_admin.py tests/test_integration_contracts.py tests/test_payment_sandbox_api.py tests/test_billing.py
pnpm --dir apps/web db:verify:stage -- --from-file .env.staging
```

## Don't

- Do not bypass server-side admin guards or mutate billing tables from the browser.
- Do not let an admin repair silently overwrite provider history; append a transition and audit reason.
- Do not run live charges, production migrations, or destructive cleanup as part of verification.
