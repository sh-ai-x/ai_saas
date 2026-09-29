# step1.md

## Status

completed

## Read first

- `PRD.md` §2 lifecycle decisions
- `apps/web/lib/payments/toss-billing.ts`
- `apps/web/lib/payments/toss-sdk.ts`
- `apps/web/app/payments/toss/billing-success/route.ts`
- `services/billing/adapters/toss.py`
- `services/billing/service.py`
- `apps/web/tests/toss-billing.test.ts`
- [Toss auto-billing API guide](https://docs.tosspayments.com/guides/v2/billing/integration-api)

## Task

Complete the provider-neutral recurring billing port and the Toss adapter/application flow. The browser must use `requestBillingAuth()` only to collect the one-time authorization result; the server issues and stores the billing-key reference, performs the first and subsequent `POST /v1/billing/{billingKey}` charge with server-owned amount/order/customer values, and persists normalized events before applying effects. Add an idempotent scheduler claim keyed by subscription and billing period because Toss does not schedule recurring calls. Implement cancellation at period end by setting local `cancel_at_period_end` and preventing the next charge, resume before period end, failed renewal with a bounded grace/retry state, expiry, verified webhook/reconcile handling, and safe duplicate/out-of-order/unknown event behavior.

## Acceptance Criteria

1. Contract tests cover billing authorization, first charge, successful renewal/next-period calculation, scheduled cancellation without immediate access loss or next charge, resume, failed renewal/grace, expiry, duplicate/out-of-order/unknown events, and reconciliation.
2. Provider calls are server-only, use test/live key separation, match customer/order/amount, and are idempotent; a redirect or client-provided status never grants entitlement.
3. The normalized internal state transition and audit records are deterministic and can recover from a missed scheduler run without double charging or double granting access.

## Verification & Status Update

```bash
pnpm --dir apps/web test -- --runInBand toss-billing payment-adapter
uv run --locked python -m unittest tests/test_billing.py tests/test_payment_sandbox_api.py tests/test_integration_contracts.py
pnpm --dir apps/web typecheck
```

## Don't

- Do not call Toss APIs from browser code or expose secret/billing keys.
- Do not cancel access immediately when a user requests period-end cancellation.
- Do not assume Toss supplies a recurring scheduler or queryable billing key after it is lost.
