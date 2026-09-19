---
id: google-oauth
category: AUTH
title: Google OAuth Live Setup
summary: Configure Google Cloud, Neon, Better Auth, and a repeatable live-login verification flow.
---
# Google OAuth Live Setup

This guide enables a real Google authorization-code flow for the web app. It
is intentionally separate from the credential-free local demo session. The
server owns the OAuth code exchange, provider tokens, session cookie, and role
decision; the browser receives only the redirect and safe session projection.

## 1. Choose the test environment

Use `APP_ENV=staging` for a live Google test, even when the app is running on
`127.0.0.1`. This makes the admin guard require the persisted server role and
prevents the local demo-admin bypass from being used accidentally.

Use a separate Google OAuth client and Neon branch for each environment when
possible:

| Environment | Browser URL | Google client | Admin behavior |
|---|---|---|---|
| Local demo | `http://127.0.0.1:3000` | none | explicit member/admin demo sessions |
| Live local test | `http://127.0.0.1:3000` | staging/test client | `app_user.role` required |
| Production | `https://YOUR_DOMAIN` | production client | `app_user.role` required |

Do not mix `localhost` and `127.0.0.1`. Google compares the scheme, host,
port, path, and trailing slash exactly.

The credential-free login page exposes two separate demo identities: **local
member** can use the workspace but cannot open `/admin`, while **local admin**
can open the admin console. This separation is useful for testing navigation
and API denial before Google credentials are configured.

## 2. Configure Google Cloud

1. Open **Google Cloud Console → APIs & Services** and select or create the
   project for this environment.
2. Open **Google Auth Platform → Branding** (or the OAuth consent screen in
   the older console) and enter the app name, support email, and developer
   contact email.
3. Choose **External** for a cross-account test. Keep the publishing status in
   **Testing** and add every account that will test login under **Audience →
   Test users**. For an internal Workspace-only app, choose **Internal** only
   when every tester belongs to that Workspace organization.
4. Request only the identity scopes needed by this template:
   `openid`, `email`, and `profile`. Do not add Drive, Calendar, or other
   sensitive scopes until the product actually uses them.
5. Under **Clients**, create an OAuth client of type **Web application**.

Google's testing mode can restrict access to allow-listed test users, and test
authorizations can expire. Add the test account before debugging the app. See
the official [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
and [Google app audience guidance](https://support.google.com/cloud/answer/15549945).

## 3. Register exact redirect URIs

Add the following to the Web application client. The OAuth callback is the API
route, not the `/auth/callback` explanatory UI page.

| Environment | Authorized JavaScript origin | Authorized redirect URI |
|---|---|---|
| Live local test | `http://127.0.0.1:3000` | `http://127.0.0.1:3000/api/auth/callback/google` |
| Production | `https://YOUR_DOMAIN` | `https://YOUR_DOMAIN/api/auth/callback/google` |

The redirect URI must match exactly. A URI registered with `localhost`, port
`3013`, a trailing slash, or a different scheme does not authorize a request
sent to `127.0.0.1:3000`.

If port `3000` is already occupied, run the current workspace on `3013` and
register this additional exact pair instead:

```text
BETTER_AUTH_URL=http://127.0.0.1:3013
http://127.0.0.1:3013/api/auth/callback/google
```

Start it with `npm run dev -- --port 3013`, then open
`http://127.0.0.1:3013/login`.

## 4. Create the runtime environment

From the web app directory:

```bash
cd apps/web
cp .env.example .env.local
```

Edit `apps/web/.env.local` with the values for the live test:

```text
APP_ENV=staging
DATABASE_URL=<Neon production-or-staging connection string>
BETTER_AUTH_URL=http://127.0.0.1:3000
BETTER_AUTH_SECRET=<long random server-only secret>
GOOGLE_CLIENT_ID=<web-client-id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<server-only-client-secret>
NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
ALLOW_LOCAL_ADMIN=false
```

Generate a local secret without committing it:

```bash
openssl rand -base64 32
```

Only `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` is browser-safe. Never put
`DATABASE_URL`, `BETTER_AUTH_SECRET`, or `GOOGLE_CLIENT_SECRET` in a
`NEXT_PUBLIC_*` variable, Markdown evidence, browser log, or Git commit.

## 5. Apply the Neon identity migration

The schema follows the `../mysaas/my-saas` Better Auth + Drizzle shape:

- `app_user`: local principal, verified email, role, and ban state.
- `account`: provider binding; Google uses `providerId=google` and the stable
  Google subject in `accountId`.
- `session`: revocable, expiring Better Auth session.
- `verification`: short-lived Better Auth verification records.

Install dependencies and migrate the configured Neon branch:

```bash
npm ci
npm run db:migrate
```

The Drizzle config reads `apps/web/.env.local` for local migration commands.
For a read-only check, export the same values in the current shell and inspect
metadata without selecting token columns:

```bash
set -a
source .env.local
set +a
psql "$DATABASE_URL" -c \
  "select tablename from pg_tables where schemaname = 'public' and tablename in ('app_user','session','account','verification') order by tablename;"
```

Expected tables: `account`, `app_user`, `session`, `verification`.

## 6. Start the web app

Keep the process running in the web app directory:

```bash
npm run dev
```

Open [http://127.0.0.1:3000/login](http://127.0.0.1:3000/login). The button
must say **Continue with Google**. If it says **Use local demo session**, the
server did not load all five live-auth values or the public feature flag is
still false.

Without live credentials, the page instead shows **Use local member session**
and **Use local admin session**. Use the member session to verify that `/app`
does not show an Admin link and that `/admin` redirects back to login.

## 7. Execute the live login test

1. Open `/login` in the same browser origin as `BETTER_AUTH_URL`.
2. Select **Continue with Google**.
3. Choose an account listed in Google Cloud **Test users**.
4. Accept the identity scopes.
5. Confirm Google returns to `/app`, not an error page.
6. Confirm the navigation shows the Google display name and the session
   control offers **Sign out**.
7. Call `/api/auth/session` in the browser or with the session cookie. The
   JSON may contain user id, email, display name, role, and expiry only. It
   must not contain `accessToken`, `refreshToken`, `idToken`, or the session
   token.
8. Select **Sign out**, then confirm `/api/auth/session` returns
   `{"session":null}` and `/login` is shown again.

The authorization code and provider tokens are handled by Better Auth on the
server. Do not copy them from the URL or browser network log into an issue.

## 8. Verify account persistence and admin role

Use read-only queries that exclude token columns:

```sql
select id, email, "emailVerified", role, "createdAt"
from app_user
where email = '<your-test-email>';

select "providerId", "accountId", "userId", "createdAt"
from account
where "providerId" = 'google'
  and "userId" = '<user-id-from-app_user>';

select id, "userId", "expiresAt", "createdAt"
from session
where "userId" = '<user-id-from-app_user>'
order by "createdAt" desc;
```

To test the admin boundary, promote only the intended test identity in the
staging database, then sign out and sign in again:

```sql
update app_user
set role = 'admin', "updatedAt" = now()
where email = '<your-test-email>';
```

Open `/admin` after the new session is established. A Google login without
`app_user.role` set to `admin` or `super_admin` must be denied. Email domain
alone never grants admin access. A newly created Google user starts as a
regular user; role promotion is an explicit server-side operation.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| `redirect_uri_mismatch` | Browser origin, port, path, scheme, and trailing slash match the Google client exactly. |
| `access_denied` or test-user warning | Add the account under Google Cloud **Audience → Test users** or publish the app when ready. |
| Button says local demo | `APP_ENV`, `BETTER_AUTH_URL`, database, Google client values, and `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true` were not loaded by the web process. |
| `auth_not_configured` | The server intentionally failed closed because one required live-auth value is missing. Restart after editing `.env.local`. |
| `/admin` redirects to login | The Google user exists but `app_user.role` is not `admin`/`super_admin`, or the session predates the role change. |
| `invalid_client` | Client ID/secret belong to a different Google Cloud project or environment. Rotate the secret in the deployment secret store. |
| OAuth works, but DB migration fails | Run `npm run db:migrate` from `apps/web` and confirm `DATABASE_URL` points to the intended Neon branch. |

## 10. Production handoff

Before production, create a separate HTTPS OAuth client and replace every
local URI with the production domain. Verify the domain, provide a public
homepage/privacy policy if required, review requested scopes, and move the
Google app out of Testing only after the test flow is stable. Keep staging and
production client secrets separate. Google's [production readiness guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
and [policy compliance guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)
describe the publishing and verification requirements.

For credential-free development, remove the live values and use the explicit
local demo button. That mode is not evidence of a successful Google OAuth
exchange.
