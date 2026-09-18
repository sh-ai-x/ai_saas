---
doc_id: billing-payment-webhooks-ledger
domain: billing
purpose: Define provider webhook verification, idempotent event processing, and credit effects.
read_when:
  - adding or debugging Lemon Squeezy or Toss Payments
  - handling duplicate, delayed, failed, refunded, or replayed payment events
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - provider-adapter-architecture.md
  - providers/lemon-squeezy.md
  - providers/toss-payments.md
  - subscriptions-and-entitlements.md
  - ../admin/operations-and-audit.md
source_of_truth: contract
owner: billing-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Payment Webhooks and Ledger

## Baseline from `mysaas`

`../mysaas/my-saas/src/app/api/webhooks/stripe/route.ts:429-499` reads the raw
body when signature verification is configured and dispatches known events.
`src/app/api/webhooks/stripe/route.ts:48-109` uses a checkout session ID as a
payment identity for duplicate credit protection. The PayPal webhook handler
at `src/app/api/webhooks/paypal/route.ts:145-189` verifies provider webhook
signatures before processing events. `src/db/schema/credits.ts:19-50` stores
payment IDs and metadata with credit transactions.

## Provider-neutral processing contract

```text
receive
  -> read raw body
  -> verify signature/secret
  -> validate event envelope
  -> persist raw event and provider event ID
  -> deduplicate
  -> map provider status to internal event
  -> apply entitlement/credit transition transactionally
  -> append audit/outbox effect
  -> acknowledge provider
```

The handler must be safe when the same event is delivered more than once, when
events arrive out of order, and when processing fails after persistence but
before acknowledgement.

## Provider adapter boundary

Provider-specific behavior is owned by separate contracts:

- [Payment provider adapter architecture](provider-adapter-architecture.md)
  defines capability ports, registry selection, normalized events, and the
  extension checklist.
- [Lemon Squeezy contract](providers/lemon-squeezy.md) defines raw-body
  signature verification, subscription states, event allowlists, and provider
  retry/replay behavior.
- [Toss Payments contract](providers/toss-payments.md) defines request/auth/
  confirmation, idempotency, billing keys, payment queries, event-specific
  webhook proof, and provider retry behavior.

The common contract must not assume that every provider has the same webhook
signature, event ID, subscription model, confirmation API, or retry semantics.

## Credit ledger contract

Every credit effect contains:

- `user_id` or tenant identity
- provider and provider event/payment identity
- internal idempotency key
- `credit_type`, positive amount, and effect type (`credit`, `debit`,
  `expired`, `refund`, or `admin_adjustment`)
- expiration policy
- reason and metadata
- created time and correlation ID

The displayed balance may be cached for fast reads, but the ledger is the
explainable history. Grants and debits must use a transaction or a concurrency
safe equivalent; a read-then-write race must not double-spend or double-grant.

## Reconciliation and replay

Operators must be able to locate an event by provider event or transmission
identity when available, payment ID, order ID, subscription ID, user ID, or
internal idempotency key. Replay must re-run the same dedupe and state-
transition rules. Manual correction requires the admin contract and never
deletes the original event.

## Related documents

- [Payment provider adapter architecture](provider-adapter-architecture.md)
- [Lemon Squeezy contract](providers/lemon-squeezy.md)
- [Toss Payments contract](providers/toss-payments.md)
- [Subscriptions and entitlements](subscriptions-and-entitlements.md)
- [Admin operations and audit](../admin/operations-and-audit.md)

## Verification evidence

- Provider-proof tests reject modified bodies, invalid signatures, missing
  secrets, and invalid server-side status queries according to each adapter.
- Duplicate delivery tests produce exactly one entitlement or credit effect.
- Concurrent delivery tests prove unique constraints or transactional guards.
- Out-of-order tests do not regress a newer entitlement to an older state.
- Sandbox replay tests cover success, failure, cancellation, refund, and retry.

## Sources

- [Lemon Squeezy webhooks](https://docs.lemonsqueezy.com/help/webhooks)
- [Lemon Squeezy webhook synchronization](https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)
- [Toss Payments API](https://docs.tosspayments.com/en/api-guide)
- [Toss Payments webhooks](https://docs.tosspayments.com/en/webhooks)
- [Toss Payments webhook events](https://docs.tosspayments.com/reference/using-api/webhook-events)
- Baseline: `../mysaas/my-saas/src/app/api/webhooks/stripe/route.ts:48-109,429-499`,
  `src/app/api/webhooks/paypal/route.ts:145-189`,
  `src/db/schema/credits.ts:19-50`.
