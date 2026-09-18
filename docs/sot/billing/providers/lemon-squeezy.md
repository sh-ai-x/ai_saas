---
doc_id: billing-provider-lemon-squeezy
domain: billing
purpose: Define the Lemon Squeezy checkout, subscription, webhook, and reconciliation contract.
read_when:
  - integrating Lemon Squeezy checkout or subscriptions
  - debugging Lemon Squeezy webhook delivery, status, refund, or entitlement drift
  - changing Lemon Squeezy product, variant, or custom checkout data mappings
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

# Lemon Squeezy Billing and Webhook Contract

## Scope

This document owns Lemon Squeezy-specific hosted checkout, subscription
status, webhook verification, event normalization, and reconciliation. The
provider-neutral ledger and entitlement rules remain authoritative for local
state and access decisions.

## Baseline from `mysaas`

`../mysaas/my-saas/src/db/schema/plans.ts:25-70` includes provider-specific
plan identifiers, including Lemon Squeezy mappings. User provider identifiers
and credit effects are represented in `src/db/schema/user.ts:16-46` and
`src/db/schema/credits.ts:19-50`. Existing Stripe/PayPal handlers are useful
patterns for webhook dispatch and signature boundaries, but this document does
not claim that `mysaas` already implements a complete Lemon Squeezy adapter.

## Provider facts and adapter responsibility

Lemon Squeezy webhooks are configured with a callback URL, signing secret, and
event list. The provider sends the signature in `X-Signature`; verification
must hash the signing secret with the raw request body and compare the result.
**(source: https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)**

The adapter owns:

- hosted checkout URL and internal order/custom-data mapping
- store, product, variant, customer, order, order-item, and subscription IDs
- webhook raw-body verification and event allowlisting
- provider event/status normalization
- provider API reads for reconciliation and provider-specific management

The adapter must not grant a local plan or credit directly. It emits a
normalized event to the provider-neutral inbox and domain transition.

## Provider identity mapping

| Lemon Squeezy value | Local use | Rule |
|---|---|---|
| `store_id` | merchant-account boundary | Bind to configured environment and store; reject unexpected store IDs. |
| `product_id` / `variant_id` | plan catalog mapping | Map the exact variant to a plan/version; never map by display name. |
| `customer_id` | external customer reference | Store as a provider reference linked to the local user/tenant. |
| `order_id` / `order_item_id` | billing order and purchase identity | Preserve both for support, refund, and reconciliation. |
| subscription resource ID | recurring subscription reference | Use as the subscription transition key. |
| `meta.custom_data` | internal user/tenant/order correlation | Use only as a correlation hint; validate against the pending local order. |

The webhook payload may include customer email and customer portal URLs. Email
is not an account identity proof, and signed portal URLs must not be copied to
logs or exposed outside the intended user flow.

## Subscription status map

The provider API uses `on_trial`, `active`, `paused`, `past_due`, `unpaid`,
`cancelled`, and `expired`. **(source:
https://docs.lemonsqueezy.com/api/subscriptions/the-subscription-object)**

| Lemon Squeezy status | Internal state | Default access policy | Required action |
|---|---|---|---|
| `on_trial` | `trialing` | allow | Record trial end and plan snapshot. |
| `active` | `active` | allow | Refresh renewal and external references. |
| `paused` | `paused` | allow while product policy permits | Record pause mode/resume time; do not silently delete access. |
| `past_due` | `past_due` | allow during configured recovery window | Mark billing attention and await recovery/failure event. |
| `unpaid` | `unpaid` | product policy must be explicit; default preserve until reconciliation | Do not guess from a client page; monitor dunning/expiry. |
| `cancelled` | `cancelled` | allow until `ends_at` | Preserve access through the defined period end. |
| `expired` | `expired` | deny | Transition to the configured default plan. |

Lemon Squeezy's subscription guidance says access should generally remain in
all statuses except `expired`; the product may impose a stricter policy only
when documented in the entitlement contract. **(source:
https://docs.lemonsqueezy.com/help/products/subscriptions)**

## Normal flow

1. Create a pending local order containing user/tenant, plan version, amount,
   currency, and expected Lemon variant.
2. Create or open the hosted checkout with only validated internal custom data.
3. Treat checkout completion as a user-experience signal, not entitlement
   proof.
4. Receive a signed webhook, preserve the raw body/hash, and identify the
   provider event and resource IDs.
5. Deduplicate, normalize the event, and apply the local entitlement/credit
   transition once.
6. Store renewal, cancellation, expiry, and customer-portal references needed
   for support and reconciliation.

Lemon Squeezy documents events including `order_created`, `order_refunded`,
`subscription_created`, `subscription_updated`, `subscription_cancelled`,
`subscription_resumed`, `subscription_expired`, `subscription_paused`,
`subscription_unpaused`, `subscription_payment_failed`,
`subscription_payment_success`, and `subscription_payment_recovered`.
**(source: https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)**

## Webhook contract

1. Read and retain the raw request body before JSON parsing.
2. Compute and constant-time compare the `X-Signature` value using the
   configured signing secret and raw body.
3. Reject invalid signatures and unexpected store/resource mappings.
4. Persist provider event name, resource type/ID, payload hash, received time,
   test/live mode, and processing state.
5. Return HTTP 200 only after durable acceptance into the inbox. Processing may
   continue asynchronously, but the event must be replayable.
6. Map only allowlisted events; quarantine unknown events without changing
   entitlement.

Lemon Squeezy documents automatic retries when the endpoint does not return
HTTP 200 and supports viewing/resending recent events from its webhook area.
**(source: https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)**

## Failure flow

- Invalid or missing signature: reject; log provider, endpoint, payload hash,
  and correlation data without storing the payload as an error message.
- Duplicate delivery: return a successful no-op after inbox dedupe.
- Event persisted but transition failed: leave the event retryable and replay
  through the same transition path.
- Out-of-order subscription event: compare effective timestamps/resource state;
  query Lemon Squeezy before applying an ambiguous regression.
- Unknown variant or customer mapping: quarantine and alert; never grant a
  default plan based on email or product name.
- `past_due`/`unpaid`: preserve historical events, follow the explicit local
  access policy, and wait for recovery or expiry rather than deleting records.
- Refund: append a refund/reversal effect linked to the original order/event;
  never erase the original credit or entitlement event.

## Security and cost implications

Keep the signing secret and API credentials in managed server-side secrets.
Verify the exact raw bytes, restrict events to the minimum required list, and
redact email, portal URLs, and payment metadata from traces. Webhook replay,
provider reads, and reconciliation jobs must be rate-limited and idempotent.
Do not create a second credit grant because the provider retries after a slow
response.

## Verification evidence

- HMAC tests cover valid, modified-body, wrong-secret, missing-header, and
  malformed-payload cases.
- Sandbox/test-mode fixtures cover every enabled event and unknown-event
  quarantine.
- Duplicate, out-of-order, delayed, and replayed webhook tests produce one
  deterministic local effect.
- Status-transition tests cover trial, pause, past due, unpaid, cancellation
  through `ends_at`, expiry, recovery, and refund.
- Reconciliation can find an event by provider resource ID, order ID,
  subscription ID, local order ID, or user/tenant.

## Related documents

- [Payment provider adapter architecture](../provider-adapter-architecture.md)
- [Provider-neutral payment webhooks and ledger](../payment-webhooks-and-ledger.md)
- [Subscriptions and entitlements](../subscriptions-and-entitlements.md)
- [Billing and admin runbook](../../billing-and-admin-runbook.md)
- [Verification, release, and incident response](../../verification/release-and-incident.md)

## Sources

- [Lemon Squeezy webhooks](https://docs.lemonsqueezy.com/help/webhooks)
- [Lemon Squeezy webhook synchronization guide](https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)
- [Lemon Squeezy subscription lifecycle](https://docs.lemonsqueezy.com/help/products/subscriptions)
- [Lemon Squeezy subscription object](https://docs.lemonsqueezy.com/api/subscriptions/the-subscription-object)
- Baseline: `../mysaas/my-saas/src/db/schema/plans.ts:25-70`,
  `src/db/schema/user.ts:16-46`, `src/db/schema/credits.ts:19-50`,
  `src/app/api/webhooks/stripe/route.ts:48-109,429-499`.
