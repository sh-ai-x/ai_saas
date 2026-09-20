# step0.md

## Status

completed

## Read first

- `PRD.md`
- `apps/web/lib/pricing/repository.ts`
- `apps/web/lib/payments/catalog-checkout.ts`
- `apps/web/components/pricing-catalog.tsx`
- `apps/web/app/payments/toss/success/route.ts`
- `services/billing/adapters/toss.py`
- `services/billing/service.py`
- `services/billing/store.py`
- `apps/web/db/schema/pricing.ts`
- The official Toss Payments MCP findings recorded in `PRD.md` §2.

## Task

Implement the end-to-end Toss Payments V2 sandbox subscription path with TDD.
Start by adding focused failing contract tests and run them to capture RED.
Then implement the smallest production change that turns the tests GREEN, and
finish with refactoring plus the declared verification commands.

The browser flow must use `requestBillingAuth()` for subscription options and
must never receive a secret key or a billing key. The server must persist the
pending order before redirecting, compare the provider/customer/order/amount
against server-owned values, exchange `authKey` for a billing key with the
server-only secret, approve the first sandbox charge through the recurring
billing API, and apply the existing entitlement/credit effect exactly once.
Keep the one-time Toss flow working and do not route the SDK JavaScript URL as
a hosted checkout URL.

Admin enabling of Toss must be a real sandbox activation path: in local/test
profiles the enabled provider setting must be honored even when the example
environment defaults to `mock`; enabling sandbox Toss must fail closed unless
matching test client and secret keys are configured. Live-looking keys must not
be accepted while sandbox mode is on. Keep provider secrets in runtime
environment variables and pass the required sandbox values to every container
that needs them.

Add or update the local setup guide so it explains test-key issuance, the
official `tosspayments-integration-guide` MCP setup, generated
`APP_SECRET_KEY`, the localhost:3000 checkout steps, test-card/auth behavior,
and the boundary between sandbox and real payments. Update tests for the
admin toggle, provider selection, subscription billing-auth context, server
confirmation, amount/order mismatch rejection, idempotency, and secret
redaction. Do not make a live payment request.

## Acceptance Criteria

1. A subscription option opened from `/billing` calls Toss V2
   `requestBillingAuth()` with a server-created order/customer context, and a
   one-time option still calls `requestPayment()`; no response or browser
   payload contains `TOSS_SECRET_KEY` or a billing key.
2. The billing-auth success path issues a billing key and approves the first
   sandbox recurring charge using the matching server-owned amount, customer,
   and order; mismatch, missing, duplicate, cancelled, and provider-error
   paths fail closed without a second entitlement or credit grant.
3. Enabling Toss in `/admin/payments` selects Toss for local/test checkout,
   requires sandbox-compatible configuration, preserves the audit reason, and
   does not silently enable a live provider or conflict with another live
   provider.
4. Compose/env configuration passes the Toss sandbox keys and generated app
   secret safely, and the setup guide gives a reproducible localhost:3000
   sandbox test procedure including MCP setup and troubleshooting.
5. The focused web and Python contract suites, type check, and full relevant
   billing tests pass with zero real-charge credentials or live payment calls.

## Verification & Status Update

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
uv run --locked python -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py tests/test_integration_contracts.py
```

## Don't

- Do not add live payment keys, real card data, or committed `.env.local`
  files.
- Do not treat a browser redirect as proof of payment without server-side
  verification and idempotent settlement.
- Do not add production scheduling, refunds, webhook tunnels, or a second
  payment provider to this phase.
