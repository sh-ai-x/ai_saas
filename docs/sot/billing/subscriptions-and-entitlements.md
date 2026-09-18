---
doc_id: billing-subscriptions-entitlements
domain: billing
purpose: Define plans, quotas, subscription lifecycle, and user entitlement state.
read_when:
  - changing plans, pricing, quotas, subscriptions, or access rules
  - handling a subscription status transition
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../auth/google-oauth.md
  - provider-adapter-architecture.md
  - providers/lemon-squeezy.md
  - providers/toss-payments.md
  - payment-webhooks-and-ledger.md
source_of_truth: contract
owner: billing-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Subscriptions and Entitlements

## Baseline from `mysaas`

`../mysaas/my-saas/src/db/schema/plans.ts:25-70` models monthly, yearly, and
one-time prices, provider identifiers, and quotas. `src/db/schema/user.ts:16-46`
stores the current `planId` and provider customer/subscription identifiers.
`src/lib/plans/getUserPlan.ts:8-40`, `updatePlan.ts:9-38`, and
`downgradeToDefaultPlan.ts:8-35` centralize plan lookup, update, and fallback.

## Contract

- A **plan** is a product catalog record; an **entitlement** is the access
  state granted to a user or tenant.
- Provider IDs are mappings, not entitlement truth. They identify the external
  product/variant/subscription used to produce an event.
- Entitlement changes originate from verified provider events or an explicitly
  audited admin action.
- Client checkout success pages may display status but cannot grant access.
- All plan changes are idempotent by provider event/payment identity.
- The default/free plan is an explicit fallback, not an implicit null state.
- Quota definitions are versioned or snapshotted when a paid event is applied
  so later catalog edits do not rewrite historical entitlement decisions.

## Provider-specific contracts

The provider-neutral lifecycle is implemented through the capability-based
adapter boundary. Read the relevant provider contract before adding or
changing a status mapping:

- [Payment provider adapter architecture](provider-adapter-architecture.md)
- [Lemon Squeezy](providers/lemon-squeezy.md)
- [Toss Payments](providers/toss-payments.md)

## Provider-neutral lifecycle

The internal lifecycle must support at least:

```text
pending -> trialing -> active -> past_due -> unpaid -> expired
                      |          |
                      +-> cancelled (access until defined end)
```

Provider status mappings are documented in the payment adapter contract and
must be re-checked against the provider's current official documentation.
Lemon Squeezy describes subscription states including trial, active, paused,
past due, unpaid, cancelled, and expired. **(source:
https://docs.lemonsqueezy.com/help/products/subscriptions)**

## Normal flow

1. A user selects a plan and starts provider checkout.
2. The provider creates or updates the external customer/subscription.
3. A signed webhook is persisted and mapped to the internal lifecycle.
4. The entitlement transition and relevant credit grant are applied once.
5. The user record exposes the current plan for fast authorization checks.
6. The event ledger remains available for audit and reconciliation.

## Cancellation, failure, and refund

- Cancellation preserves access until the contractually defined period end.
- Payment failure moves the entitlement according to the provider-neutral
  mapping; it does not immediately delete historical records.
- Expiry removes paid access and returns the user to the configured default
  plan through the common transition use case.
- Refunds reverse or annotate the original entitlement/credit effect according
  to the product policy; they never silently delete the original event.
- Unknown provider states fail closed for new access and enter reconciliation.

## Admin relationship

Admin plan changes must use the same entitlement transition contract and must
record actor, reason, before state, after state, and whether provider state is
also being changed. See [admin/operations-and-audit.md](../admin/operations-and-audit.md).

## Verification evidence

- State-transition tests cover every provider mapping, duplicate event,
  out-of-order event, cancellation, failure, recovery, expiry, and refund.
- Reconciliation compares provider state, local event ledger, user entitlement,
  and credit effects.
- Historical entitlement decisions remain explainable from event IDs and
  catalog snapshots.

## Sources

- [Lemon Squeezy subscriptions](https://docs.lemonsqueezy.com/help/products/subscriptions)
- [Lemon Squeezy webhook synchronization](https://docs.lemonsqueezy.com/guides/developer-guide/webhooks)
- Baseline: `../mysaas/my-saas/src/db/schema/plans.ts:25-70`,
  `src/db/schema/user.ts:16-46`, `src/lib/plans/updatePlan.ts:9-38`,
  `src/lib/plans/downgradeToDefaultPlan.ts:8-35`.
