# plan → build hand-off

## Plan

- Phase: `toss-subscription-sandbox`
- Branch/worktree: `feat/subscription-toss-payment`
- Proposal: `docs/proposals/reviewing/toss-payment/subscription-sandbox.html`
- Goal: connect the existing subscription catalog and admin Toss enable switch to a verified Toss Payments V2 sandbox flow at localhost:3000 without real charging.
- Methodology: TDD — capture RED first, implement GREEN, refactor, then run the declared web and Python verification commands.

## Evidence-driven decisions

- Use `requestBillingAuth()` for subscription options, not `requestPayment()`.
- Keep the secret key and billing key server-side.
- Persist and validate the server-owned order, amount, currency, provider, and customer identity before the first recurring approval.
- Treat the existing idempotent order/entitlement/credit path as the settlement authority.
- Let an enabled persisted Toss setting drive local/test selection while requiring sandbox-compatible runtime keys.

## Build order

1. Step 0: `toss-subscription-sandbox-e2e` — red-first contracts and end-to-end implementation for browser handoff, server billing-key exchange, first recurring sandbox charge, admin enablement, configuration, and setup guide.

## Required verification

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
uv run --locked python -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py tests/test_integration_contracts.py
```

## Safety boundary

Do not add live keys, real card data, or live payment calls. Production recurring scheduling, dunning, refunds, and webhook tunnel operations are explicitly deferred.

## Next hand-off

On success, continue to `/dev-kit:review` and `/dev-kit:security`; inspect the per-step two-commit protocol and verification evidence before any release action.
