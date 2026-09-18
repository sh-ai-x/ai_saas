# Lemon Squeezy sandbox

Select Lemon Squeezy as the only live adapter for the environment:

```bash
PAYMENT_PROVIDER=lemon-squeezy
PAYMENT_SANDBOX=true
MOCK_PAYMENTS_ENABLED=false
LEMONSQUEEZY_API_KEY=test-mode-server-key
LEMONSQUEEZY_WEBHOOK_SECRET=server-only-secret
```

Create the pending order with `POST /v1/billing/orders`. Register
`POST /v1/billing/webhooks/lemon-squeezy`; the API verifies `X-Signature` over
the raw body, checks order/status/idempotency, then applies the shared ledger.

```bash
python3 -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py
```

Browser redirects never grant credits, and replaying a signed event cannot
grant credits twice.
