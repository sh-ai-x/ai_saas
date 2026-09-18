# Sandbox payments

## Provider rule

Select exactly one real provider per environment. Toss and Lemon Squeezy have
different checkout semantics, so the adapter contract normalizes them at the
order, webhook, and ledger boundary. Never configure both credentials at once.

## Toss sandbox

```bash
cp config/profiles/toss-sandbox.example.env .env
# fill test_* keys outside Git
python3 -m foundation.config --env-file .env --profile free-portfolio
```

The web console creates a pending order. The Toss widget/SDK completes the
customer flow; the API then validates `paymentKey`, `orderId`, and exact amount
at `POST /v1/billing/toss/confirm`. Register the webhook endpoint:

```text
POST https://<public-api>/v1/billing/webhooks/toss
```

## Lemon Squeezy test mode

```bash
cp config/profiles/lemon-squeezy-sandbox.example.env .env
# fill test-mode API and signing values outside Git
python3 -m foundation.config --env-file .env --profile free-portfolio
```

Register:

```text
POST https://<public-api>/v1/billing/webhooks/lemon-squeezy
```

The adapter verifies `X-Signature` against the raw body, normalizes the event,
and applies the ledger once. A duplicate delivery returns `applied=false`.

## Safety

`PAYMENT_SANDBOX=true` is mandatory outside production. The client success
redirect never grants credits. The server persists the pending order before
checkout and only a confirmed/reconciled provider event changes entitlement or
credits.

```bash
python3 -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py
```
