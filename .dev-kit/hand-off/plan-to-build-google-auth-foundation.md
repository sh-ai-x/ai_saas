# Plan → Build Handoff — Google Auth Identity Extension

## Baseline

The pricing/admin foundation from the previous extension is carried into this
worktree. This plan adds the `mysaas`-referenced Better Auth + Drizzle Google
identity boundary without changing the one-active-billing-mode contract.

## Build order

1. `google-auth-data-model` — `app_user`, `session`, `account`, and
   `verification` tables plus migration and SOT.
2. `google-auth-runtime` — Better Auth Drizzle adapter, Google provider,
   server route handler, session projection, and admin role enforcement.
3. `google-auth-surfaces` — login/sign-out/callback UI and route navigation.
4. `google-auth-verification` — tests, browser smoke, setup guide, and exact
   output evidence.

## Guardrails

- Local/test uses the existing deterministic demo profile without Google
  credentials.
- Production requires `DATABASE_URL`, `BETTER_AUTH_SECRET`,
  `BETTER_AUTH_URL`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`.
- Provider tokens and OAuth codes stay server-side. No secret enters source,
  logs, fixtures, screenshots, or the browser bundle.
- Google authentication proves identity only; admin, tenant, billing, and
  agent authorization remain separate server-side checks.
