---
doc_id: billing-provider-toss-payments
domain: billing
purpose: Define Toss Payments one-time, recurring billing, webhook, cancellation, and reconciliation contracts.
read_when:
  - integrating or changing Toss Payments
  - debugging payment confirmation, virtual-account, billing-key, webhook, or refund behavior
  - changing Korean payment methods, MID, test/live keys, or Toss provider mappings
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../../00-index.md
  - ../provider-adapter-architecture.md
  - ../subscriptions-and-entitlements.md
  - ../payment-webhooks-and-ledger.md
  - ../../admin/operations-and-audit.md
source_of_truth: contract
owner: billing-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Toss Payments Billing and Webhook Contract

## Scope

This document owns Toss Payments-specific one-time payment request/auth/
confirmation, payment query and cancellation, virtual-account events,
optional recurring billing with billing keys, webhook verification, and
reconciliation. The provider-neutral ledger and entitlement contract own local
access and credit effects.

## Baseline from `mysaas`

`../mysaas/my-saas/src/db/schema/plans.ts:25-70` models provider IDs and
quotas, while `src/db/schema/user.ts:16-46` and
`src/db/schema/credits.ts:19-50` provide the user/provider-reference and
ledger baseline. The existing Stripe/PayPal webhook code demonstrates the
need for provider-specific verification and dedupe, but no Toss-specific
behavior is assumed to already exist.

## Provider facts and adapter responsibility

Toss Payment APIs use server-side secret-key authentication. The current API
guide documents an `Idempotency-Key` for POST requests, with a unique random
value up to 300 characters and a 15-day validity period. **(source:
https://docs.tosspayments.com/en/api-guide)**

The adapter owns:

- client-safe checkout initialization versus server-only API calls
- `orderId`, `paymentKey`, `customerKey`, `billingKey`, MID, and environment
  mapping
- amount/currency validation before confirmation
- confirm, query, cancel, and billing-key API translation
- webhook payload verification/query policy and event normalization

The browser success redirect never grants entitlement. The server must verify
the local pending order and complete the provider confirmation/query path.

## Credential and environment contract

| Value | Boundary | Rule |
|---|---|---|
| client key | browser SDK/widget boundary | Use only for the configured product/MID and matching test/live environment. |
| secret key | server adapter boundary | Never expose to browser, logs, agent context, or trace payloads. |
| `test_*` keys | sandbox | Keep separate from live configuration; no real charge. |
| `live_*` keys | production | Require deployment approval and managed secret injection. |
| MID | provider merchant-account boundary | Bind each capability/service to the correct MID; do not mix key sets. |
| `customerKey` | local-to-provider customer binding | Use an unpredictable stable local identifier; do not use raw email or phone. |

Toss documents separate test/live key prefixes and warns that secret keys must
not be exposed. **(source:
https://docs.tosspayments.com/reference/using-api/api-keys)**

## One-time payment contract

The current Toss flow separates request, customer authentication, and server
approval. The success URL provides `paymentKey`, `orderId`, and `amount`; the
server must compare these with the pending order before calling
`POST /v1/payments/confirm`. **(source:
https://docs.tosspayments.com/guides/v2/get-started/payment-flow)**

### Normal flow

1. Create a local pending order with an immutable amount, currency, plan
   snapshot, and unique `orderId`.
2. Start the client checkout using the configured client key/MID.
3. On success redirect, send the returned fields to the server over the
   authenticated session; do not trust them as the expected amount.
4. Load the pending order and require exact `orderId` and amount equality.
5. Call the confirm API with the server secret and a stable idempotency key.
6. Persist `paymentKey` and the provider response; only a confirmed successful
   payment enters the entitlement/credit transition.
7. Reconcile with payment query and `PAYMENT_STATUS_CHANGED` where applicable.

Toss's API guide documents the confirm and payment-query APIs, and the
payment-flow guide requires server-side verification between redirect and
approval. **(source: https://docs.tosspayments.com/en/api-guide)**

### Idempotency

The idempotency key is generated per local payment attempt and persisted with
the order. A network retry reuses the same key; it must not generate a second
payment attempt with a different key unless an operator-approved recovery path
creates a new attempt. The same rule applies to cancellation/refund POSTs.

## Recurring billing contract

Toss recurring billing requires a billing-key contract and an application-owned
scheduler. A customer is authenticated before the billing key is issued; the
server stores the billing key securely with its `customerKey` binding and uses
it for each scheduled charge. Toss states that it does not provide the
scheduling function, so the product must own scheduling, retries, and
subscription state transitions. **(source:
https://docs.tosspayments.com/guides/v2/billing/integration)**

Rules:

- Treat the billing key as a high-sensitivity provider credential/token.
- Never store raw card data; store only provider tokens and minimal metadata.
- Bind each billing key to the same stable `customerKey` used at issuance.
- Create a durable billing attempt before calling the recurring-charge API.
- Use a unique persisted idempotency key per scheduled charge attempt.
- On success, record the provider response and append the entitlement/credit
  effect once.
- On failure, keep the subscription and attempt histories; notify, retry only
  according to a bounded policy, and move to the internal delinquent state.
- Cancellation stops future scheduler calls and may delete the billing key via
  the provider flow; it does not erase historical charges.

Toss's billing guide describes billing-key registration and recurring approval
as an application-managed subscription flow. **(source:
https://docs.tosspayments.com/guides/billing/overview)**

## Webhook contract

The primary payment events are:

- `PAYMENT_STATUS_CHANGED` for one-time payment status updates
- `DEPOSIT_CALLBACK` for virtual-account issuance/deposit/cancellation
- `CANCEL_STATUS_CHANGED` for supported asynchronous foreign payment flows

The webhook payload includes an event type, creation time, and payment data.
For virtual-account callbacks, the provider supplies a `secret` that must be
matched with the payment response. If both `PAYMENT_STATUS_CHANGED` and
`DEPOSIT_CALLBACK` are registered, the same virtual-account change can be
delivered twice. **(source:
https://docs.tosspayments.com/reference/using-api/webhook-events)**

Current Toss documentation exposes transmission time, retry count, and
transmission ID headers. The generic payment-status events do not use the
same HMAC signature flow as payout/seller events; therefore the adapter must
re-query the payment by `paymentKey` with the server secret and compare the
returned state before applying a financial effect. **(source:
https://docs.tosspayments.com/guides/v2/get-started/llms-quick-reference)**

Webhook processing:

1. Parse only after retaining the raw request and headers.
2. Record transmission ID/retry metadata, payment key/order ID, event type,
   payload hash, and received time.
3. Query Toss for the authoritative payment state when the event is a general
   payment status notification.
4. Validate virtual-account callback proof against the stored payment secret.
5. Deduplicate by provider transmission identity plus a stable payment/state
   key; do not assume every payment event has a generic `eventId`.
6. Persist before returning HTTP 200; transition entitlement/ledger through the
   provider-neutral contract.

Toss retries a webhook when the endpoint does not return HTTP 200, up to seven
resends according to its current webhook guide. **(source:
https://docs.tosspayments.com/en/webhooks)**

## Cancellation and refund contract

Use `POST /v1/payments/{paymentKey}/cancel` with a server secret, explicit
reason, and a persisted idempotency key. Toss supports full and partial
cancellations with payment-method-specific requirements. **(source:
https://docs.tosspayments.com/en/api-guide)**

A cancellation request is an intent, not permission to delete local history.
Persist the request, provider result, cancel amount, reason, operator or
system actor, and resulting ledger reversal/annotation. Admin-initiated
cancellation must use the admin audit contract.

## Failure flow

- Success redirect with wrong amount/order: reject confirmation and alert on
  possible tampering.
- Confirm timeout or ambiguous response: query by `paymentKey` before retrying;
  reuse the same idempotency key for a safe retry.
- Duplicate webhook: dedupe and return a no-op.
- General webhook without cryptographic signature: verify by server-side query;
  never trust payload status alone.
- Virtual-account duplicate registration: dedupe the overlapping events.
- `DONE`/deposit state conflict: query Toss, preserve both raw events, and
  reconcile before changing access.
- Billing-key charge failure: create a failed attempt, bounded retry or
  payment-method-update path, and do not silently revoke historical access.
- Unknown payment state: quarantine and fail closed for new entitlement.

## Security and cost implications

Keep secret keys, billing keys, and payment response payloads out of browser
logs, agent context, and general observability payloads. Validate key/MID and
test/live pairing at startup. Bound confirmation retries, scheduler retries,
webhook queries, and reconciliation to avoid duplicate charges and provider
rate-limit cost. Use network controls as defense in depth; they do not replace
provider-state verification.

## Verification evidence

- Sandbox tests cover request/auth/confirm success, failure, wrong amount,
  duplicate confirm, cancellation, partial cancellation, and query recovery.
- Idempotency tests confirm retries reuse the persisted key and do not create
  duplicate local effects.
- Webhook tests cover transmission metadata, duplicate deliveries, retry,
  `PAYMENT_STATUS_CHANGED`, `DEPOSIT_CALLBACK`, and invalid virtual-account
  proof.
- Timer/state tests cover the payment authorization/confirmation expiry path
  and asynchronous virtual-account reconciliation.
- Recurring tests cover billing-key/customer binding, scheduler retry, charge
  failure, cancellation, and missing/rotated billing key.
- Secret scanning and trace-redaction tests prove client keys/secret keys,
  billing keys, and unnecessary payment data are excluded from logs.

## Related documents

- [Payment provider adapter architecture](../provider-adapter-architecture.md)
- [Provider-neutral payment webhooks and ledger](../payment-webhooks-and-ledger.md)
- [Subscriptions and entitlements](../subscriptions-and-entitlements.md)
- [Billing and admin runbook](../../billing-and-admin-runbook.md)
- [Admin operations and audit](../../admin/operations-and-audit.md)
- [Verification, release, and incident response](../../verification/release-and-incident.md)

## Sources

- [Toss Payments API guide](https://docs.tosspayments.com/en/api-guide)
- [Toss Payments payment flow](https://docs.tosspayments.com/guides/v2/get-started/payment-flow)
- [Toss Payments webhooks](https://docs.tosspayments.com/en/webhooks)
- [Toss Payments webhook events](https://docs.tosspayments.com/reference/using-api/webhook-events)
- [Toss Payments API keys](https://docs.tosspayments.com/reference/using-api/api-keys)
- [Toss Payments billing integration](https://docs.tosspayments.com/guides/v2/billing/integration)
- [Toss Payments billing overview](https://docs.tosspayments.com/guides/billing/overview)
- Baseline: `../mysaas/my-saas/src/db/schema/plans.ts:25-70`,
  `src/db/schema/user.ts:16-46`, `src/db/schema/credits.ts:19-50`,
  `src/app/api/webhooks/stripe/route.ts:48-109,429-499`.
