---
id: payment-toss
category: PAYMENT / TOSS
title: Toss Payments sandbox
summary: Configure the Toss sandbox adapter, server confirmation, and exactly-once ledger settlement.
---
# Toss Payments sandbox

Use Toss as the only live payment adapter in this environment. The browser
may open the Toss sandbox checkout, but the API owns the pending order,
confirmation, amount comparison, and credit ledger effect.

## 1. Configure the sandbox

```bash
PAYMENT_PROVIDER=toss
PAYMENT_SANDBOX=true
MOCK_PAYMENTS_ENABLED=false
TOSS_CLIENT_KEY=test_ck_...
TOSS_SECRET_KEY=test_sk_...
TOSS_WEBHOOK_SECRET=server-only-secret
```

## 2. Create the pending order

```text
POST /v1/billing/orders
-> order_id, provider_reference, checkout_url, test_mode=true
```

Persist the returned order ID and compare the amount and currency with the
server-owned order before accepting any browser success result.

## 3. Confirm server-side

```text
POST /v1/billing/toss/confirm
{ "order_id": "...", "payment_key": "...", "amount_minor": 1000 }
```

The API calls Toss confirmation with the server secret, rejects an amount or
order mismatch, normalizes the result, and applies credits through the common
idempotent ledger path.

## 4. Verify and recover

```bash
python3 -m unittest tests/test_payment_sandbox_api.py
```

Duplicate confirmation or webhook delivery is a no-op. Invalid signatures,
unknown orders, and amount mismatches fail closed.
