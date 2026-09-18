# Toss Payments sandbox

Select Toss as the only live adapter for the environment:

```bash
PAYMENT_PROVIDER=toss
PAYMENT_SANDBOX=true
MOCK_PAYMENTS_ENABLED=false
TOSS_CLIENT_KEY=test_ck_...
TOSS_SECRET_KEY=test_sk_...
TOSS_WEBHOOK_SECRET=server-only-secret
```

Create the pending order with `POST /v1/billing/orders`. After the Toss sandbox
flow, call `POST /v1/billing/toss/confirm` with `order_id`, `payment_key`, and
the exact server-owned amount. The API confirms with the secret key, normalizes
the event, and applies credits through the common idempotent ledger.

```bash
python3 -m unittest tests/test_payment_sandbox_api.py
```

Invalid signatures, unknown orders, amount mismatches, and duplicate delivery
fail closed or become no-ops.
