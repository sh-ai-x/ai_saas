---
id: pricing-admin
category: ADMIN
title: Pricing and admin console
summary: Configure Neon-backed plans, one-time products, subscriptions, and provider-safe settings without placing admin controls on the landing page.
---
# Pricing and admin console

The product has three distinct surfaces: `/` is public landing and catalog,
`/app` is the authenticated workspace, and `/admin` is the server-guarded
policy console. The landing page consumes active catalog records; it does not
own pricing.

## 1. Apply the Neon migration

Copy `apps/web/.env.example` to `.env.local`, set `APP_ENV=local`, and add the
Neon production branch URL as `DATABASE_URL`. Apply the committed migration
from the generated SQL migration in `apps/web/drizzle/` with the repository's Neon
migration workflow. The migration creates plan policy, purchase options,
provider settings, order/subscription state, billing inbox, and audit tables.

```bash
cd apps/web
npx drizzle-kit migrate
```

## 2. Open the separate admin console

Run the web app, then open `http://127.0.0.1:3000/admin`. Local mode allows the
explicit local admin guard. A deployed environment must set
`ALLOW_LOCAL_ADMIN=false`, provide `APP_ENV=production`, and configure the
server-only `ADMIN_API_TOKEN` before admin mutations are allowed.

```bash
npm run dev
open http://127.0.0.1:3000/admin/pricing
```

## 3. Configure a plan

Choose the catalog billing model in `/admin/payments` first: exactly one of
`one_time` or `subscription`. Then create a plan policy and add only valid
options. A one-time product uses `mode=one_time` and `interval=one_time`; a
subscription product uses `mode=subscription` and `interval=month` or `year`.
For example, an annual $290 subscription and a $79 one-time product are
separate product policies and are never shown together as choices in one
active catalog. Amounts are integer minor currency units and the checkout API
resolves them from the database by `optionId`; browser input cannot override
the amount.

## 4. Configure provider adapters

Keep `mock` enabled for local development. For a sandbox, set exactly one of
`PAYMENT_PROVIDER=toss` or `PAYMENT_PROVIDER=lemon-squeezy` and provide the
provider's sandbox values through runtime environment variables. Admin public
configuration may contain store, variant, or client identifiers; API keys and
signing secrets never belong in PostgreSQL or browser JSON.

## 5. Verify the purchase flow

From `/`, select a one-time or recurring option. The web server loads the
option, resolves the provider, creates a normalized checkout intent, and
returns browser-safe handoff data. A redirect is only UX state. A verified
provider event must create the order/subscription and ledger/entitlement
effect exactly once.

## 6. Local fallback boundary

If `DATABASE_URL` is omitted in local/test mode, the repository uses the
explicit seeded catalog and labels the source as `local-seed`. This is useful
for portfolio demos and type/API checks, but it is not a production database.
Production fails closed when the Neon URL is missing.
