---
id: pricing-admin
category: ADMIN
title: Pricing and admin console
summary: Configure one active billing model, Neon-backed plans, and provider-safe payment settings.
---

# Pricing and admin console

The product has three distinct surfaces: `/` is public landing and catalog,
`/app` is the user workspace, and `/admin` is the server-guarded policy
console. Public pricing reads active catalog records; it does not own pricing.

## 1. Select one billing model

In `/admin/payments`, select exactly one catalog mode: `subscription` or
`one_time`. Subscription plans can expose monthly and yearly options. A
one-time product exposes only a one-time option. The seeded Toss-compatible
catalog keeps the existing option IDs and displays the annual Pro option as
₩29,000 and the one-time product as ₩7,900.

## 2. Configure the catalog

Create or edit plans at `/admin/pricing`. Amounts are integer minor currency
units and the checkout API resolves them from the database by `optionId`.
Client input cannot override amount, currency, interval, or billing mode.

## 3. Apply the Neon migration

Set `DATABASE_URL` from the linked Neon production branch and apply the
committed Drizzle migration:

```bash
pnpm install
pnpm --filter ai-saas-foundation-web db:migrate
```

The schema includes `pricing_catalog_settings`, `pricing_plans`,
`pricing_options`, `payment_provider_settings`, `payment_orders`,
`subscriptions`, `billing_events`, and `admin_audit_events`.

## 4. Keep provider secrets out of the database

Use `PAYMENT_PROVIDER=mock` locally when deterministic checkout is needed. For
the Toss sandbox, set `PAYMENT_PROVIDER=toss`; the existing Starter/Pro
options are reused after the KRW migration. Safe public identifiers may be
stored in admin settings; API keys and signing secrets stay in environment
variables or a secret manager.

## 5. Verify dynamic checkout

Open `/billing` and choose an option. The server resolves the active mode and
catalog row, then returns browser-safe adapter handoff data. Switching the
admin billing mode changes `/`, `/billing`, and checkout validation together.
A redirect is not entitlement proof; only a verified provider event can apply
an order, subscription, ledger, or entitlement effect.
