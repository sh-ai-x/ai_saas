Status: completed
Name: sandbox-payment-provider

Task:
Connect the existing adapter ports to real Toss and Lemon Squeezy sandbox
requests. Add authenticated checkout/confirmation routes and raw webhook
endpoints while preserving one-provider selection and the atomic ledger.

Acceptance:
- `PAYMENT_PROVIDER=toss` or `lemon-squeezy` is the only enabled live adapter;
  local/staging configuration requires sandbox/test mode.
- Pending orders are created before redirects; client success data is compared
  with the pending order before provider confirmation.
- Raw webhook signatures, provider status, amount, and idempotency are checked
  before effects are applied exactly once.
- No mock completion route is available when a real provider is selected.

Verification:
```bash
python3 -m unittest tests/test_payment_sandbox_api.py
```
