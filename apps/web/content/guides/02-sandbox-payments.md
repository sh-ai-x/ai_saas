---
id: payments
category: PAYMENTS
title: Sandbox payments
summary: Connect exactly one Toss or Lemon Squeezy sandbox adapter at a time.
---
# Sandbox payments

## 1. Select one provider

Toss and Lemon Squeezy share the order, webhook, idempotency, and ledger
contract. Do not configure both in one environment. Local and staging require
sandbox mode.

```bash
PAYMENT_PROVIDER=toss
PAYMENT_SANDBOX=true
MOCK_PAYMENTS_ENABLED=false
TOSS_SECRET_KEY=test_...
TOSS_WEBHOOK_SECRET=server-only-secret
```

For Lemon Squeezy use `LEMONSQUEEZY_API_KEY` and
`LEMONSQUEEZY_WEBHOOK_SECRET` from test mode instead.

## 2. Confirm and reconcile

Create the pending order first. Toss validates `paymentKey`, `orderId`, and
amount server-side. Lemon Squeezy accepts only a verified signed webhook.

```text
POST /v1/billing/orders
POST /v1/billing/toss/confirm
POST /v1/billing/webhooks/toss
POST /v1/billing/webhooks/lemon-squeezy
```

Duplicate delivery is a no-op and cannot grant credits twice.

## 3. Go live deliberately

Keep `PAYMENT_SANDBOX=true` until sandbox evidence exists. Production requires
an explicit reviewed change, managed secrets, and one selected provider.
