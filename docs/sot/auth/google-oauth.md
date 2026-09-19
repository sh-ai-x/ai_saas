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

## Database contract

The implementation follows the Better Auth + Drizzle shape used by the
`mysaas` reference. The schema names are intentionally stable so the web
console, API routes, and future identity service can share a migration:

| Table | Responsibility | Required boundary |
|---|---|---|
| `app_user` | Local principal, verified email, display profile, role, ban state | Google subject is not the local primary key; role is server-controlled |
| `session` | Revocable browser/server session, token, expiry, client metadata | Token is unique, expiring, httpOnly-cookie backed, and never serialized to UI |
| `account` | External provider binding and provider token metadata | `providerId=google`; stable Google subject in `accountId`; secrets remain server-only |
| `verification` | Better Auth verification records and expiry | Values are short-lived and never logged or returned |

The `account` table is the identity-linking authority: a changed Google email
does not create a new local user when the provider subject is unchanged. The
`app_user.role` value is checked by the admin boundary; email domain or Google
login status alone is not sufficient for privileged access.

## Runtime profiles

- `local`: demo session and deterministic mock sign-in remain available without
  Google credentials; no provider redirect is attempted.
- `test`: callback validation and session contracts use deterministic fixtures;
  no network token exchange is required.
- `staging`/`production`: `DATABASE_URL`, `BETTER_AUTH_SECRET`,
  `BETTER_AUTH_URL`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` are
  mandatory. The server returns a configuration error before redirect when any
  required value is missing.

The production migration must be applied before enabling the callback route.
The browser receives only the authorization URL, safe session projection, and
safe error category; authorization codes, ID tokens, access tokens, refresh
tokens, and client secrets stay server-side.

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

- Deterministic contract tests cover local sign-in, httpOnly cookie behavior,
  safe session projection, production fail-closed configuration, local
  sign-out, and admin denial without a configured session.
- Better Auth owns provider callback state validation, code exchange, and
  account persistence. Replay, mismatched-state, expired-code, collision, and
  provider-outage cases require a configured staging OAuth client and are not
  claimed as credential-free automated tests.
- Logs contain correlation IDs and outcome categories, never client secrets or
  raw authorization codes.

## Sources

- [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
- Baseline: `../mysaas/my-saas/src/auth.ts:24-35,81-87`,
  `src/proxy.ts:15-63`, `src/lib/auth/withSuperAdminAuthRequired.ts:14-50`.
