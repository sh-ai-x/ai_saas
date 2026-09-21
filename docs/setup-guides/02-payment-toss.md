---
id: payment-toss
category: PAYMENT / TOSS
title: Toss Payments sandbox subscription setup
summary: Configure matching test keys, the official Integration Guide MCP, Admin Toss enablement, and the localhost:3000 subscription sandbox.
---
# Toss Payments sandbox subscription setup

This app uses Toss Payments V2 Standard JavaScript SDK for browser handoff and
server APIs for billing-key issuance, recurring approval, and one-time payment
confirmation. Local/test mode is sandbox-only and never charges a real card.

## 1. Obtain matching test keys

Open the [Toss Developer Center API keys](https://developers.tosspayments.com/my/api-keys),
sign in, and select the test store/MID. Copy the matching client/secret pair;
both sandbox values start with `test_`. The MCP does not issue keys. Do not
combine keys from different stores, commit them, put the secret in
`NEXT_PUBLIC_*`, or return it in browser JSON.

```bash
export TOSS_CLIENT_KEY="test_ck_your_client_key"
export TOSS_SECRET_KEY="test_sk_your_matching_secret_key"
export PAYMENT_SANDBOX=true
export PAYMENT_PROVIDER=toss
export MOCK_PAYMENTS_ENABLED=false
export WEB_PAYMENT_PROVIDER=toss
export TOSS_SDK_SANDBOX_RESULT=SUCCESS
```

## 2. Connect the official Toss Integration Guide MCP

The correct MCP server is named `tosspayments-integration-guide`; the package
is `@tosspayments/integration-guide-mcp`, not `toss-pay-mcp`.

```toml
[mcp_servers.tosspayments-integration-guide]
command = "npx"
args = ["-y", "@tosspayments/integration-guide-mcp@latest"]
```

Restart the MCP client/session, then search for `자동결제(빌링)`, `구독`, or
`billingKey`. The official references used by this integration are:

- [Billing overview](https://docs.tosspayments.com/guides/v2/billing)
- [Billing checkout integration](https://docs.tosspayments.com/guides/v2/billing/integration)
- [Billing API integration](https://docs.tosspayments.com/guides/v2/billing/integration-api)
- [API keys](https://docs.tosspayments.com/reference/using-api/api-keys)

## 3. Start localhost safely

The Foundation container requires a generated secret, which fixes the common
`APP_SECRET_KEY must be a generated value with at least 32 characters` startup
error:

```bash
cp .env.docker.example .env
export APP_SECRET_KEY="$(openssl rand -hex 32)"
export TOSS_CLIENT_KEY="test_ck_your_client_key"
export TOSS_SECRET_KEY="test_sk_your_matching_secret_key"
export PAYMENT_SANDBOX=true
export TOSS_SUCCESS_URL="http://localhost:3000/payments/toss/success"
export TOSS_BILLING_SUCCESS_URL="http://localhost:3000/payments/toss/billing-success"
export TOSS_FAIL_URL="http://localhost:3000/payments/toss/fail"
docker compose -f docker/prod/compose.yaml up --build
```

The provider variables are required when Toss credentials are present:
`PAYMENT_PROVIDER=toss` selects the Foundation provider, `WEB_PAYMENT_PROVIDER=toss`
selects the web adapter, and `MOCK_PAYMENTS_ENABLED=false` prevents the mock/live
configuration conflict. The admin enable action still persists the provider
setting and audit event; the environment variables only supply the sandbox
runtime and credentials.

Open [http://localhost:3000/guides?guide=payment-toss](http://localhost:3000/guides?guide=payment-toss).
The Foundation health endpoint is [http://localhost:8080/healthz](http://localhost:8080/healthz).

## 4. Enable Toss on the existing Starter/Pro catalog

1. Sign in with the configured Google test account and open
   `/admin/payments`.
2. Keep the billing mode on **Subscription**, then enable **Toss**. The API
   requires both matching test keys and disables the other active provider.
3. The migration converts the existing Starter and Pro option IDs to KRW while
   preserving their amounts and IDs. Do not create a second Toss plan or a
   separate Toss mock option.
4. Open `/billing` and choose the existing Starter or Pro subscription. When
   Toss is active, the same option is projected as a Toss option and opens
   `requestBillingAuth()`.

Toss general card payments support KRW. The migration is idempotent and updates
existing USD rows only; a missing migration must be fixed before checkout rather
than converted in the browser.

## 5. Subscription sandbox flow

From `/billing`, select the active Toss subscription:

```text
POST /api/pricing/checkout
  -> persist pending payment_orders
  -> browser payment.requestBillingAuth()
  -> /payments/toss/billing-success?customerKey=...&authKey=...
  -> POST /v1/billing/authorizations/issue (server secret)
  -> POST /v1/billing/{billingKey} (server secret + idempotency key)
  -> mark the order succeeded and persist the subscription
```

The browser receives only the client key, random customer key, amount, order,
and redirect URLs. It never receives `TOSS_SECRET_KEY` or `billingKey`. The
server compares customer, order, amount, KRW currency, status, and provider
against its pending order before settlement. If Toss asks for a test
authentication code, enter `000000`.

When `PAYMENT_SANDBOX=true` and the client key starts with `test_`, the web
checkout also sends the V2 SDK sandbox simulation parameter:
`sandbox: { paymentResult: "SUCCESS" }`. This completes authentication without
requiring a card. Set `TOSS_SDK_SANDBOX_RESULT=FAIL` to exercise the failure
redirect instead. The simulation is rejected for live client keys, and the
server still performs the normal test-key confirmation and order checks.

For one-time mode, switch Admin billing policy to One-time, configure a KRW
Toss option, and the browser calls `requestPayment()`. The success route then
calls `/v1/payments/confirm` server-side and applies the same amount/order and
idempotency checks.

## 6. Scope and troubleshooting

- Live Toss mode is not enabled in local/test profiles. Automatic billing may
  require a Toss risk review/contract before production use.
- Toss does not schedule recurring approvals. A reviewed scheduler must call
  the billing approval API for later periods; this phase covers the first
  sandbox charge only.
- `UNAUTHORIZED_KEY`: re-copy a matching client/secret pair from the same
  Developer Center test store.
- `MOCK_PAYMENTS_ENABLED` conflict: use `PAYMENT_PROVIDER=toss`,
  `WEB_PAYMENT_PROVIDER=toss`, and `MOCK_PAYMENTS_ENABLED=false` with Toss
  credentials.
- Missing-key admin error: both `TOSS_CLIENT_KEY` and `TOSS_SECRET_KEY` must be
  present in the web runtime and start with `test_` while sandbox is enabled.
- Currency error: run the web migration and verify `option-pro-monthly` or
  `option-pro-yearly` is KRW; do not create a duplicate Toss option.
- `toss mcp unknown`: use the exact server/package names above and restart the
  MCP client; MCP documentation access is separate from Toss key issuance.

Deterministic checks do not call Toss:

```bash
pnpm --dir apps/web lint
pnpm --dir apps/web test
uv run --locked python -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py tests/test_integration_contracts.py
```
