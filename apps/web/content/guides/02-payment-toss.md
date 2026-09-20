---
id: payment-toss
category: PAYMENT / TOSS
title: Toss Payments sandbox subscription setup
summary: Get matching test keys, connect the official Toss integration-guide MCP, enable Toss from Admin, and verify a no-charge subscription flow on localhost.
---
# Toss Payments sandbox subscription setup

This project uses the Toss Payments V2 Standard JavaScript SDK for the browser
handoff and the server API for every secret-key operation. Local and staging
configuration is sandbox-only: test keys begin with `test_`, and no real card
is charged. The first subscription charge is approved in the success callback;
periodic renewals still require a scheduler and are intentionally outside this
local setup flow.

## 1. Get Toss test keys

1. Open the [Toss Payments Developer Center API keys](https://developers.tosspayments.com/my/api-keys).
2. Sign in and select the test store/MID. A test client key and its matching
   test secret key are shown even before a live electronic-payment contract.
3. Copy the pair without changing either value. The pair must belong to the
   same store and environment. For sandbox work, the values must start with
   `test_` (for example `test_ck_...` and `test_sk_...`).
4. Keep the client key in the server runtime because this app injects it into
   the browser-safe checkout context. Never expose `TOSS_SECRET_KEY` in React,
   `NEXT_PUBLIC_*`, PostgreSQL JSON, Git, or logs.

If you do not have a Toss account yet, the official billing guide also provides
document test keys. Use only the matching pair shown by Toss; do not combine a
client key from one store with a secret key from another.

## 2. Connect the official Toss MCP guide

The correct server is Toss Payments' **Integration Guide MCP**, not a server
named `toss-pay` or `toss-payment`. It searches the official V2 guides and
returns the source document used to implement this flow.

Install/use it through the MCP client configuration:

```toml
[mcp_servers.tosspayments-integration-guide]
command = "npx"
args = ["-y", "@tosspayments/integration-guide-mcp@latest"]
```

The package name is:

```text
@tosspayments/integration-guide-mcp
```

After saving the MCP configuration, restart the Codex/agent session and check
the MCP status. The server should expose document search, document-by-ID, and
glossary-document tools. Search for `자동결제(빌링)`, `구독`, or `billingKey`.
The implementation decisions in this page follow the official documents:

- [Automatic billing overview](https://docs.tosspayments.com/guides/v2/billing)
- [Billing checkout integration](https://docs.tosspayments.com/guides/v2/billing/integration)
- [Billing API integration](https://docs.tosspayments.com/guides/v2/billing/integration-api)
- [API keys](https://docs.tosspayments.com/reference/using-api/api-keys)

MCP does not issue API keys and does not replace the Developer Center. It is a
documentation lookup server; credentials still come from the Toss Developer
Center and stay in the app runtime.

## 3. Configure local environment safely

Create a local ignored env file or export the values in the shell. Do not put
real keys in a committed example file.

```bash
cp .env.docker.example .env
export APP_SECRET_KEY="$(openssl rand -hex 32)"

export PAYMENT_SANDBOX=true
export TOSS_CLIENT_KEY="test_ck_your_matching_client_key"
export TOSS_SECRET_KEY="test_sk_your_matching_secret_key"
export TOSS_SUCCESS_URL="http://localhost:3000/payments/toss/success"
export TOSS_BILLING_SUCCESS_URL="http://localhost:3000/payments/toss/billing-success"
export TOSS_FAIL_URL="http://localhost:3000/payments/toss/fail"
```

The `APP_SECRET_KEY` must be a generated value with at least 32 characters.
Without it, the Foundation container exits with:
`APP_SECRET_KEY must be a generated value with at least 32 characters`.
Never use a placeholder such as `change-me`.

For Docker Compose, put the exported values in the ignored root `.env` file
or run Compose with those variables present:

```bash
docker compose -f docker/prod/compose.yaml up --build
```

Open [http://localhost:3000](http://localhost:3000). The Foundation health
check is [http://localhost:8080/healthz](http://localhost:8080/healthz).

## 4. Prepare a Toss-compatible catalog

Toss general card payments support `KRW`. The seeded catalog is intentionally
provider-neutral and currently contains USD mock options, so changing the
provider alone must not silently change the price or currency.

1. Sign in with the configured Google test account.
2. Open [Admin payment settings](http://localhost:3000/admin/payments).
3. Keep the catalog mode on **Subscription** for this flow.
4. Enable **Toss**. The server checks that both matching sandbox keys exist;
   enabling Toss automatically disables the other active provider.
5. Open [Admin pricing](http://localhost:3000/admin/pricing).
6. Edit the subscription option you want to test so its provider is **Toss**,
   currency is **KRW**, and amount is a positive integer in won. For example,
   `29000` means ₩29,000. Save with an audit reason.
7. Keep only the option you intend to test active. The checkout API always
   loads the amount and currency from this server-side catalog; browser input
   cannot override them.

If an option remains USD or still points to mock, checkout fails closed with a
clear configuration error instead of sending an invalid Toss request.

## 5. Run a subscription sandbox checkout

Open [Billing](http://localhost:3000/billing), choose the active KRW Toss
subscription, and click the option. The flow is:

```text
browser -> POST /api/pricing/checkout
        -> persist pending payment_orders row
        -> Toss requestBillingAuth()
        -> /payments/toss/billing-success?customerKey=...&authKey=...
        -> server POST /v1/billing/authorizations/issue
        -> server POST /v1/billing/{billingKey}
        -> mark order succeeded + persist subscription
```

`customerKey` is generated randomly for the pending order. `authKey` is used
once to exchange the card authorization for a `billingKey`; the billing key
and secret key never return to the browser. The approval request validates
the server-owned order ID and amount and sends an idempotency key.

In the Toss sandbox, if a card-authentication code is requested, enter
`000000`. Test keys and the sandbox test card flow do not charge a real card.
If the browser is redirected to the fail URL, inspect the user-facing error
and retry with the matching test key pair; do not switch to live keys.

## 6. One-time payment behavior

Switch the catalog policy to **One-time** in Admin, create/select a KRW Toss
one-time option, and use the same Billing page. The SDK calls
`requestPayment()` instead of `requestBillingAuth()`. The success callback
calls `/v1/payments/confirm` on the server, validates `paymentKey`, `orderId`,
amount, status, and idempotency, then marks the pending order succeeded.

## 7. What this setup does not do

- It never enables live Toss mode on a local/test `APP_ENV`.
- It does not send Toss secret keys to the client or store them in the catalog.
- It does not treat a redirect as payment proof; the server approval response
  is required.
- It does not run recurring renewal scheduling. Toss requires the merchant to
  call the billing approval API at the desired period, so add a reviewed cron
  or job worker before using this for production subscriptions.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| `APP_SECRET_KEY` rejected | Generate `openssl rand -hex 32` and restart Compose. |
| `toss mcp unknown` | Use the exact server/package name `tosspayments-integration-guide` / `@tosspayments/integration-guide-mcp`; restart the MCP client. |
| Admin enable returns missing-key error | Set both `TOSS_CLIENT_KEY` and `TOSS_SECRET_KEY` in the web runtime; the pair must be `test_` keys when `PAYMENT_SANDBOX=true`. |
| Checkout says currency must be KRW | Edit the active Toss pricing option in Admin pricing; do not convert the amount in the browser. |
| `UNAUTHORIZED_KEY` from Toss | The client/secret pair is mismatched, truncated, or from a different store/MID. Copy both again from API keys. |
| Billing auth succeeds but approval fails | Confirm the pending order still has the same customer key, order ID, amount, and KRW option; retry is protected by the order idempotency key. |

Run the deterministic checks without contacting Toss:

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
uv run --locked python -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py tests/test_integration_contracts.py
```
