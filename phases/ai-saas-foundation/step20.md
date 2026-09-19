Status: pending
Name: google-auth-data-model

## Read first

- `PRD.md` §9 and REQ-19–REQ-23
- `docs/sot/auth/google-oauth.md`
- `docs/sot/security/safety-boundaries.md`
- `../mysaas/my-saas/src/db/schema/user.ts`
- `apps/web/db/schema/pricing.ts`

## Task

Design and implement the Better Auth-compatible Drizzle identity schema for
Google login. Add local user, session, provider account, and verification
tables with explicit foreign keys, unique identities, expiry fields, role
state, and safe column boundaries. Add a reproducible PostgreSQL migration and
update the Google OAuth SOT with the final table names and ownership.

## Acceptance Criteria

- `app_user`, `session`, `account`, and `verification` are authoritative in
  `apps/web/db/schema/auth.ts` and exported by the schema index.
- Google provider identity is represented by `account.provider_id` and a
  stable provider subject; session tokens and provider secrets are never
  seeded, logged, or returned by a UI projection.
- Foreign keys cascade user-owned rows; session token and provider identity
  uniqueness are enforced by the migration.
- The migration is idempotent according to the existing Drizzle convention
  and does not alter pricing table ownership.
- Typecheck and Drizzle schema checks pass without requiring Google credentials.

## Verification & Status Update

Record real commands and measured results in `step20-output.json` before
marking the step complete.

## Don't

- Do not copy pricing data into the identity tables.
- Do not store `GOOGLE_CLIENT_SECRET` or a real OAuth token in seed data.
- Do not make admin authorization depend only on the user's email address.
