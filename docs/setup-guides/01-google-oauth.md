---
id: google-oauth
category: AUTH
title: Google OAuth
summary: Configure Better Auth, Drizzle identity tables, and a server-side Google callback.
---

# Google OAuth

## 1. Google Cloud Console

Create an OAuth 2.0 Web application client. Add these exact redirect URIs:

```text
http://127.0.0.1:3000/api/auth/callback/google
https://YOUR_DOMAIN/api/auth/callback/google
```

Use separate credentials for local, staging, and production when possible.

## 2. Runtime environment

```text
APP_ENV=staging
DATABASE_URL=<server-only Neon connection string>
BETTER_AUTH_URL=https://YOUR_DOMAIN
BETTER_AUTH_SECRET=<random server secret>
GOOGLE_CLIENT_ID=<google web client id>
GOOGLE_CLIENT_SECRET=<server-only google client secret>
NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
```

Only `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` is browser-safe. All other values stay
in the deployment secret manager or ignored local environment files.

## 3. Database migration

The Drizzle migration creates `app_user`, `session`, `account`, and
`verification`. `account` links `providerId=google` to the immutable Google
subject; `app_user.role` controls admin access. Run:

```bash
npm run db:migrate
```

## 4. Local verification

Start the web app and open `/login`. Without Google credentials, use the local
demo session. With credentials, select **Continue with Google** and confirm the
browser returns to `/app`. The server route owns the authorization code,
tokens, state, and session cookie.

```bash
npm run lint
npm run test
```

Production rejects incomplete auth configuration. Google login alone never
grants billing access, tenant membership, or admin permissions.
