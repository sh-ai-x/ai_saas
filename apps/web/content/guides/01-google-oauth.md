---
id: google-oauth
category: AUTH
title: Google OAuth
summary: Configure the server-side authorization-code flow and browser callback.
---
# Google OAuth

## 1. Create OAuth credentials

In Google Cloud Console, create an OAuth 2.0 Web application client. Add the
exact Better Auth callback URL for each environment. For local development,
the callback is handled by the server route; the browser never receives a
client secret.

```text
http://127.0.0.1:3000/api/auth/callback/google
```

For staging or production, add the deployed HTTPS URL using the same path:
`https://YOUR_DOMAIN/api/auth/callback/google`.

## 2. Configure runtime secrets

```bash
APP_ENV=staging
DATABASE_URL=server-only-neon-connection-string
BETTER_AUTH_URL=https://YOUR_DOMAIN
BETTER_AUTH_SECRET=generate-a-long-random-server-secret
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=server-only-secret
NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
```

Never commit these values or place them in `NEXT_PUBLIC_*` variables except for
the boolean feature flag. `BETTER_AUTH_SECRET`, `GOOGLE_CLIENT_SECRET`, and
`DATABASE_URL` must stay in the deployment secret store.

## 3. Apply identity tables

The Drizzle migration creates the Better Auth-compatible identity boundary:

- `app_user`: local principal, verified email, role, and ban state.
- `account`: provider binding; Google uses `providerId=google` and the stable
  Google subject in `accountId`.
- `session`: revocable, expiring server sessions.
- `verification`: short-lived Better Auth verification records.

Run the migration from the web app directory:

```bash
npm run db:migrate
```

## 4. Start sign-in

Open `/login` and select **Continue with Google**. Better Auth handles the
authorization-code exchange through `/api/auth/[...all]`. The server validates
state, redirect origin, provider configuration, and the returned identity before
creating a session. The UI receives only a safe user/session projection.

For local work without Google Cloud credentials, select **Use local demo
session**. This profile is intentionally deterministic and does not call
Google.

## 5. Verify the security boundary

```bash
npm run lint
npm run test
```

The tests verify local session creation, httpOnly cookie behavior, production
fail-closed configuration, safe session projection, sign-out, and that a
missing Google configuration never starts an OAuth redirect. Do not use a live
Google account in deterministic tests.

## 6. Admin and account-linking rules

Google login proves identity only. Admin access still requires the server-side
`app_user.role` (`admin` or `super_admin`), and billing entitlements are read
from the billing catalog/ledger. A changed email does not change the account
when the Google subject is the same. Explicit account-linking confirmation is
required when an email collision points to another local user.
