---
doc_id: billing-provider-adapter-architecture
domain: billing
purpose: Define the extensible payment-provider boundary using ports, capability adapters, and a provider registry.
read_when:
  - adding a payment provider
  - changing provider selection, payment capabilities, or billing orchestration
  - reviewing whether provider-specific behavior is leaking into domain logic
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
  - subscriptions-and-entitlements.md
  - payment-webhooks-and-ledger.md
  - ../admin/operations-and-audit.md
  - ../verification/release-and-incident.md
source_of_truth: contract
owner: billing-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Payment Provider Adapter Architecture

## Scope

This document defines how the product talks to multiple payment providers. It
covers checkout, payment confirmation, recurring billing, refunds, webhook
verification, event normalization, provider selection, and reconciliation. It
does not define the commercial meaning of plans or entitlements; those remain
in [subscriptions and entitlements](subscriptions-and-entitlements.md).

## Decision

Use a Ports-and-Adapters boundary, commonly implemented with provider
adapters behind application-owned interfaces. “Adapter” is the right local
pattern, but it must be combined with capability interfaces and a registry.
Do not create one giant interface that forces every provider to implement
features it does not support. Fowler describes a gateway as translating the
application's types and operations to an external API and as an anti-corruption
boundary. **(source: https://martinfowler.com/articles/gateway-pattern.html)**

The payment domain owns the invariant; each provider adapter owns translation
to a provider's API, status vocabulary, credentials, retry semantics, and
webhook envelope.

## Why this fits `mysaas`

`../mysaas/my-saas/src/db/schema/plans.ts:25-70` already stores provider
identifiers alongside a shared plan catalog. `src/db/schema/user.ts:16-46`
stores provider customer/subscription identifiers, while
`src/app/api/webhooks/stripe/route.ts:48-109,429-499` and the PayPal webhook
handler show provider-specific verification and dispatch. The shared
`updatePlan` and `downgradeToDefaultPlan` use cases are the important seam to
preserve. The production extension is to move provider translation behind
adapters and to avoid adding a new column or branch in the domain for every
new provider.

## Design map

```text
Product billing use cases
  -> application-owned payment ports
  -> provider registry selects provider + supported capability
  -> Lemon Squeezy adapter | Toss Payments adapter | future adapter
  -> provider API / webhook endpoint

provider payload
  -> provider adapter verifies and parses
  -> normalized event
  -> durable inbox + dedupe
  -> domain transition
  -> entitlement / credit ledger / audit / outbox
```

The domain must never import a provider SDK, inspect a provider status string,
trust a client redirect, or use a provider secret. The adapter must never
decide whether a user is entitled beyond returning a verified, normalized
provider fact.

## Capability ports

| Capability | Application-owned responsibility | Lemon Squeezy | Toss Payments |
|---|---|---|---|
| Hosted checkout | Create or identify a checkout and bind internal order context | Supported through hosted checkout | Supported through checkout/widget flow |
| One-time payment confirmation | Confirm an authenticated payment | Provider-specific; do not assume a client confirmation API | `POST /v1/payments/confirm` |
| Subscription lifecycle | Create/update/cancel/read recurring subscription | Native subscription lifecycle | Requires Toss billing-key contract and application scheduler |
| Refund/cancellation | Request and record a refund/cancel intent | Provider API/dashboard workflow | Cancel API with provider-specific rules |
| Webhook verification | Verify the provider envelope before normalization | `X-Signature` against raw body | Event-specific verification/query rules |
| Status query | Reconcile external state | Subscription/order API | Payment query API by `paymentKey` |
| Event normalization | Map provider event into internal event types | Adapter-owned | Adapter-owned |

Capabilities are explicit. A provider can be registered for checkout and
webhooks without pretending to support recurring billing. Unsupported
capabilities fail with a typed configuration error before any external call.

## Provider registry contract

The registry resolves a provider using a server-controlled selection, never a
client-supplied provider name alone. A registry entry contains:

- stable provider key and adapter version
- supported capabilities
- environment and merchant-account identity
- secret references, not secret values
- API version and endpoint configuration
- enabled event allowlist
- retry, timeout, and rate-limit policy
- reconciliation query policy

Selection rules:

1. Resolve the product's configured provider for the plan, currency, region,
   and capability.
2. Verify that the selected adapter supports the requested capability.
3. Create a provider-independent internal order or billing intent first.
4. Pass only the minimum mapped fields to the adapter.
5. Persist the provider reference and idempotency identity before applying a
   domain-side entitlement or credit effect.

## Canonical internal contract

All adapters translate into the same internal records:

- `billing_order`: internal order, user/tenant, plan snapshot, amount, currency,
  status, and provider selection
- `billing_external_reference`: provider, environment, resource type, external
  ID, and internal owner
- `billing_provider_event_inbox`: provider event identity, raw payload hash,
  received time, processing state, and failure reason
- `subscription_state`: provider-neutral lifecycle plus provider status and
  effective/expiry timestamps
- `credit_transaction`: append-only grant, debit, expiry, refund, or admin
  adjustment with idempotency identity

The existing `mysaas` provider columns can be a migration baseline, but the
long-term model should use a normalized external-reference boundary when more
providers or multiple merchant accounts are introduced. Historical provider
IDs must remain queryable for support and reconciliation.

## Normal flow

1. A domain use case creates a pending internal billing order.
2. The registry selects a provider and capability from server configuration.
3. The adapter creates checkout or confirms a provider payment using the
   provider's idempotency rules.
4. The provider result or webhook is verified and stored in the inbox.
5. The adapter normalizes it into a provider-independent event.
6. The domain transition applies entitlement, credit, audit, and outbox
   effects transactionally and exactly once.
7. Reconciliation can query the provider and compare the result with the
   internal order, event inbox, entitlement, and ledger.

## Failure flow

- Unsupported capability: reject before an external request.
- Invalid signature or provider proof: reject and preserve only safe metadata.
- Duplicate event or retry: return a no-op after inbox deduplication.
- Out-of-order event: persist it, then apply only monotonic or explicitly
  reconciled state transitions.
- Provider timeout: keep the order pending/unknown and reconcile; do not grant
  access from a timed-out client request.
- Adapter bug or unknown provider status: quarantine the event and fail closed
  for new entitlement rather than guessing.
- Provider replacement: keep the normalized domain contract and historical
  references; add a new adapter and migration/reconciliation policy.

## Security and cost implications

Provider credentials are isolated in the adapter/runtime boundary and injected
from managed secrets. The domain receives redacted normalized facts, not raw
credentials or unnecessary payment data. Provider retries, polling,
reconciliation, and webhook replay are bounded by per-provider rate, time,
and cost budgets. One provider outage must not trigger unbounded fallback
charges or duplicate entitlement grants.

## Extension checklist

A new provider is not complete when checkout works. The adapter proposal must
define:

- supported capabilities and explicit unsupported capabilities
- credential and environment model
- checkout/confirm/cancel/refund semantics
- provider identifiers and amount/currency rules
- signature or server-query verification
- event identity, dedupe, ordering, and retry behavior
- provider-to-internal status map and unknown-state policy
- reconciliation queries and operator replay procedure
- sandbox/test fixtures, failure injection, and rollback plan
- privacy, retention, audit, and cost limits

## Verification evidence

- Contract tests prove each adapter satisfies only its declared capabilities.
- Provider sandbox tests cover success, duplicate, timeout, cancellation,
  refund, retry, and unknown-state cases.
- Property or state-machine tests prove adapters cannot grant entitlement
  directly and domain transitions remain idempotent.
- Replay tests use stored raw events and produce the same normalized result
  without duplicate ledger effects.
- A provider outage test proves routing, budgets, and reconciliation remain
  bounded.

## Related documents

- [Provider-neutral payment webhooks and ledger](payment-webhooks-and-ledger.md)
- [Lemon Squeezy contract](providers/lemon-squeezy.md)
- [Toss Payments contract](providers/toss-payments.md)
- [Subscriptions and entitlements](subscriptions-and-entitlements.md)
- [Admin operations and audit](../admin/operations-and-audit.md)
- [Verification, release, and incident response](../verification/release-and-incident.md)

## Sources

- [Martin Fowler: Gateway](https://martinfowler.com/articles/gateway-pattern.html)
- [Martin Fowler: Separated Interface](https://martinfowler.com/eaaCatalog/separatedInterface.html)
- Baseline: `../mysaas/my-saas/src/db/schema/plans.ts:25-70`,
  `src/db/schema/user.ts:16-46`,
  `src/app/api/webhooks/stripe/route.ts:48-109,429-499`,
  `src/lib/plans/updatePlan.ts:9-38`.
