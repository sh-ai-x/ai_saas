---
doc_id: billing-pricing-catalog-admin
domain: billing
purpose: Define the Neon/Drizzle pricing catalog, admin ownership, and checkout mode boundary.
read_when:
  - designing plans or pricing options
  - changing the admin pricing or provider settings surfaces
  - changing one-time or subscription checkout selection
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - billing/provider-adapter-architecture.md
  - billing/payment-webhooks-and-ledger.md
source_of_truth: contract
owner: platform-engineering
last_reviewed: 2026-09-19
change_impact: high
---

# Pricing Catalog and Admin SOT

**Status:** approved implementation baseline
**Scope:** public catalog, user checkout intent, admin pricing operations, and
provider configuration for the AI SaaS foundation
**Reference:** `../mysaas/my-saas`

## 1. Purpose

Pricing is controlled data, not presentation-only content. The public landing
page reads active catalog records. The user app requests checkout by an opaque
pricing-option ID. The admin console owns product policy and safe provider
configuration. Payment adapters remain the only code allowed to translate a
normalized intent into Toss, Lemon Squeezy, or mock provider calls.

## 2. Route ownership

| Surface | Route | Reads | Writes |
|---|---|---|---|
| Public landing | `/` | active plans/options | none |
| User app | `/app` | session, runs, checkout result | run and checkout intent |
| Admin console | `/admin` | plans/options/provider status/audit | plans, options, safe provider settings |
| Setup docs | `/guides` | imported Markdown | none |

The landing page must never render admin mutation controls. The admin layout is
a separate authenticated/authorized surface, even when local demo mode uses a
development admin identity.

## 3. Canonical tables

### `pricing_catalog_settings`

The platform-level policy row selects exactly one active `billing_mode`:
`one_time` or `subscription`. It also stores the catalog currency and the
operator that last changed the policy. Public catalog queries filter by this
row; checkout rejects an option from the other mode.

### `pricing_plans`

Product policy and display metadata: `id`, unique `code`, `name`,
`description`, `billing_mode`, `active`, `is_default`, `display_order`,
`features` JSONB, `quotas` JSONB, `created_at`, and `updated_at`.

### `pricing_options`

A purchasable SKU for a plan: `id`, `plan_id`, `mode` (`one_time` or
`subscription`), `interval` (`one_time`, `month`, or `year`), `provider`,
`currency`, `amount_minor`, optional `compare_at_amount_minor`, safe provider
product/price references, `active`, metadata, and timestamps.

The database enforces unique `(plan_id, mode, interval, provider)` and the
mode/interval pair. Application validation additionally requires that an
option mode matches its plan and the active catalog policy. Amounts are
integer minor units; clients cannot override them.

### `payment_provider_settings`

One row per provider with `enabled`, `sandbox`, safe `public_config` JSONB,
and `secret_ref`. `secret_ref` names an environment/secret-manager entry; it
does not contain the secret. Runtime validators require exactly one selected
live provider.

### `payment_orders` and `subscriptions`

Normalized purchase records reference the pricing option snapshot and retain
external order/customer/subscription IDs. Idempotency keys and provider event
identities are unique. One-time order status is independent from recurring
subscription status.

### `billing_events`

Provider inbox boundary: provider, external event ID, raw body hash, normalized
payload, verification status, and processed timestamp. Webhooks are verified,
deduplicated, and then converted into entitlement/ledger effects.

### `admin_audit_events`

Append-only record of actor, action, resource, reason, before JSON, after JSON,
and timestamp. Every pricing/provider mutation requires a non-empty reason.

## 4. Secret and tenant boundary

- Neon credentials, OAuth secrets, Toss secret keys, and Lemon Squeezy signing
  secrets are runtime-only.
- Safe public identifiers may be visible to admins and in browser handoff;
  secret references are never returned to public API clients.
- In the first modular-monolith deployment, table ownership is represented by
  repository/module boundaries and tenant columns. Physical service extraction
  must preserve these contracts.
- A missing `DATABASE_URL` is allowed only in an explicit local profile. It
  uses the seeded in-memory catalog and must fail closed in production.

## 5. `mysaas` adaptations

The reference has useful admin routing, plan CRUD, quotas, and provider product
IDs. This foundation splits the single `plans` record into catalog policy plus
purchasable options, makes one billing mode active at a time, separates
recurring from one-time semantics, adds order and subscription state, and
records operator audit history. This avoids hardcoded landing prices and
makes Toss/Lemon Squeezy adapters contract-compatible without storing provider
secrets in the plan row.

## 6. Verification invariant

For every checkout request:

```text
client option_id
  -> server catalog lookup
  -> validated mode/interval/provider/amount
  -> adapter checkout intent
  -> verified provider event
  -> idempotent order/subscription + ledger/entitlement effect
```

Redirects are UX signals only. A redirect never grants credit or access by
itself.
