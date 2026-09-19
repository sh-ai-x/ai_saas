---
id: payment-lemonsqueezy
category: PAYMENT / LEMON SQUEEZY
title: Lemon Squeezy sandbox
summary: Configure Lemon Squeezy test mode, signed webhooks, and exactly-once credit settlement.
---
# Lemon Squeezy sandbox

Use Lemon Squeezy as the only live payment adapter in this environment. The
adapter creates a provider checkout handoff, then accepts only a verified
signed webhook for entitlement and credit effects.

## 1. Configure test mode

```bash
PAYMENT_PROVIDER=lemon-squeezy
PAYMENT_SANDBOX=true
MOCK_PAYMENTS_ENABLED=false
LEMONSQUEEZY_API_KEY=test-mode-server-key
LEMONSQUEEZY_WEBHOOK_SECRET=server-only-secret
LEMONSQUEEZY_STORE_ID=test-store-id
LEMONSQUEEZY_VARIANT_ID=test-variant-id
LEMONSQUEEZY_REDIRECT_URL=https://your-app.example/payments/lemon-squeezy/success
```

Map the local plan to the test-mode variant in the provider dashboard. Keep
the API key and signing secret outside the browser bundle.

## 2. Create the checkout order

```text
POST /v1/billing/orders
-> order_id, provider_reference, checkout_url, checkout_context, test_mode=true
```

The adapter sends the configured store and variant as JSON:API relationships
and places the local order/tenant correlation in `checkout_data.custom`. A
plan name is never sent as a provider product ID.

The order is pending before the redirect. Do not grant credits from a browser
redirect or a client-provided status.

## 3. Receive the signed webhook

```text
POST /v1/billing/webhooks/lemon-squeezy
X-Signature: provider-signature
<raw provider body>
```

The API verifies the raw body signature, provider event identity, order amount,
status, and idempotency key before using the shared billing ledger.

## 4. Verify and reconcile

```bash
python3 -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py
```

Replay is safe: a duplicate event cannot grant credits twice. Unknown orders
and invalid signatures remain pending or fail closed for operator review.
