Status: pending
Name: pricing-data-model

## Read first

- `PRD.md` §8 and REQ-13–REQ-18
- `docs/sot/billing/provider-adapter-architecture.md`
- `docs/sot/billing/payment-webhooks-and-ledger.md`
- `docs/sot/billing/subscriptions-and-entitlements.md`
- `../mysaas/my-saas/src/db/schema/plans.ts`
- `../mysaas/my-saas/src/db/schema/user.ts`

## Task

Design and implement the database-first pricing boundary with Drizzle ORM and
Neon PostgreSQL. Add normalized plan, pricing option, provider setting, order,
subscription, billing inbox, and admin audit tables; add a committed migration
and deterministic local seed fallback. Keep provider secrets outside the
database and document the ownership/constraint decisions in the pricing SOT.

## Acceptance Criteria

- `apps/web/db/schema` contains the authoritative Drizzle schema.
- `apps/web/drizzle` contains a reproducible PostgreSQL migration.
- `pricing_catalog_settings` selects exactly one active billing mode. A
  subscription plan can have monthly/yearly options; a one-time plan cannot
  expose recurring intervals, and the two families are not mixed in the
  active catalog.
- Provider/mode/interval identities and idempotency keys have database
  constraints; secret values are not columns or seed data.
- The repository can read the seeded catalog without `DATABASE_URL`, while a
  configured Neon connection uses Drizzle.
- Typecheck and schema/config checks pass.

## Verification & Status Update

Record the exact commands, exit codes, and measured outcomes in
`step15-output.json`. Do not mark this step complete until the migration is
reviewable and the SOT agrees with the schema.

## Don't

- Do not copy the `mysaas` single-table pricing design verbatim.
- Do not store Toss, Lemon Squeezy, Google, or database secrets in PostgreSQL.
- Do not make UI work a dependency of this step.
