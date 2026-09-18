---
doc_id: auth-google-oauth
domain: auth
purpose: Define Google OAuth, session, account-linking, and authorization boundaries.
read_when:
  - implementing or changing Google login
  - changing session, account, callback, or protected-route behavior
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
  - ../security/safety-boundaries.md
source_of_truth: contract
owner: identity-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Google OAuth and Identity Contract

## Baseline

`../mysaas/my-saas/src/auth.ts:24-35,81-87` uses Better Auth with a
Drizzle/Postgres adapter and enables Google as a social provider. Its user,
session, account, and verification tables are defined in
`src/db/schema/user.ts:16-93`.

## Contract

- Google OAuth is an authorization-code web-server flow handled by a
  server-side identity layer. **(source:
  https://developers.google.com/identity/protocols/oauth2/web-server)**
- OAuth client secrets never enter browser code, agent context, logs, or
  Langfuse payloads.
- Redirect URIs are explicit per environment and exact-match validated.
- The callback validates `state`, issuer, code, redirect URI, and the returned
  identity before creating or linking a local account.
- A local session is the authorization input for Next.js protected routes,
  FastAPI agent requests, billing operations, and admin operations.
- Identity provider subject IDs are stored separately from display email so a
  changed email cannot silently become a different account.
- Account linking requires an authenticated user and an explicit confirmation
  when an email already belongs to another account.

## Normal flow

1. User selects Google sign-in.
2. The server creates an OAuth transaction and redirects to Google.
3. Google returns an authorization code to the registered callback.
4. The server exchanges and validates the code.
5. The identity is linked to an existing local user or a new user is created.
6. The session is persisted and the user is redirected to the requested safe
   destination.

## Failure and recovery

- Invalid state or callback: reject without creating a session.
- Provider timeout: show retryable error; do not create a partial account.
- Email collision: require explicit account-linking support flow.
- Expired session: return an unauthenticated response and preserve only a safe
  callback path.
- Provider outage: existing sessions continue until normal expiry; new login
  fails closed.

## Authorization boundary

Authentication proves identity. It does not grant plan entitlement, agent tool
scope, or admin privilege. Those are checked by the relevant contracts:

- Entitlement: `../billing/subscriptions-and-entitlements.md`
- Agent tools: `../agent/runtime-and-tools.md`
- Admin actions: `../admin/operations-and-audit.md`
- Safety and secrets: `../security/safety-boundaries.md`

## Verification evidence

- OAuth callback tests cover valid, replayed, mismatched-state, expired-code,
  collision, and provider-error cases.
- Protected route tests prove unauthenticated users cannot create agent runs,
  mutate billing, or access admin APIs.
- Logs contain correlation IDs and outcome categories, never client secrets or
  raw authorization codes.

## Sources

- [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
- Baseline: `../mysaas/my-saas/src/auth.ts:24-35,81-87`,
  `src/proxy.ts:15-63`, `src/lib/auth/withSuperAdminAuthRequired.ts:14-50`.
