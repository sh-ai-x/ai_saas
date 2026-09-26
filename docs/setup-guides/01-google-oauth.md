---
id: google-oauth
category: AUTH
title: Google OAuth Live Setup
summary: Configure Google Cloud, Neon, Better Auth, and a repeatable live-login verification flow.
---
# Google OAuth Live Setup

This guide enables the real Google authorization-code flow for the web app.
Google is the only user-facing account entry point: the first successful
authorization creates the account, and later authorizations sign in to that
account. The server owns the OAuth code exchange, provider tokens, session
cookie, and role decision; the browser receives only the redirect and safe
session projection. There is no local or mock login fallback.

## 1. Choose the test environment

Use `APP_ENV=staging` for a live Google test while the app runs on
`http://localhost:3000`. This makes the admin guard require the persisted
server role and keeps the test-only auth fixture unavailable.

Use a separate Google OAuth client and Neon branch for each environment when
possible:

| Environment | Browser URL | Google client | Admin behavior |
|---|---|---|---|
| Local without OAuth | `http://localhost:3000` | none | setup notice; no login fallback |
| Live local test | `http://localhost:3000` | staging/test client | `app_user.role` required |
| Production | `https://YOUR_DOMAIN` | production client | `app_user.role` required |

Use `http://localhost:3000` consistently. Google compares the scheme, host,
port, path, and trailing slash exactly.

The login page always exposes one Google action. A regular Google account can
use the user workspace, while an account whose persisted `app_user.role` is
`admin` or `super_admin` can open `/admin`. Email address, Google Workspace
domain, or which button was clicked never grants admin access.

## 2. Configure Google Cloud from the web console

Use the Google Cloud Console in a desktop browser. Google is moving the old
**APIs & Services → OAuth consent screen** flow into **Google Auth Platform**;
the labels can differ slightly between projects. The required sections are
still **Branding**, **Audience**, **Data Access**, and **Clients**.

### 2.1 Create or select the Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. In the top project selector, click **New project** or select the existing
   project dedicated to this environment.
3. Give the project a recognizable name such as `ai-saas-staging` and click
   **Create**. Keep staging and production in separate projects when possible.
4. In the left menu, open **Google Auth Platform**. If the console still shows
   the legacy layout, open **APIs & Services → OAuth consent screen** instead.
5. If Google shows **Get started** or **Configure**, click it before creating
   credentials. A client cannot be created until the OAuth app registration is
   initialized.

### 2.2 Branding: configure the consent screen

Open **Google Auth Platform → Branding** and complete the form. Use the exact
values below for a first local test; replace the placeholder URLs before
production:

| Console field | Local/staging value |
|---|---|
| App name | The product name shown on the Google consent screen, for example `AI SaaS Foundation` |
| User support email | An inbox the test user can use to contact the operator |
| App logo | Optional for local testing; use a product logo that matches the web app in production |
| App homepage | `http://localhost:3000` for this workspace, or the deployed HTTPS homepage |
| App privacy policy URL | A public HTTPS URL in production; leave unset only when the console allows a local test to proceed |
| App terms of service URL | A public HTTPS URL in production; optional during the local test if allowed |
| Developer contact information | An email monitored for Google configuration and policy notices |

Click **Save** or **Next** after each screen. Review the Google API Services
User Data Policy and click **Create/Continue** when prompted. Do not claim that
the app uses Drive, Calendar, or other Google APIs; this template only needs
Google identity information.

### 2.3 Audience: choose who may sign in

1. Open **Google Auth Platform → Audience**.
2. Select **External** when the test account is not in the same Google
   Workspace organization as the Cloud project. Select **Internal** only when
   every user belongs to the owning Workspace organization.
3. Keep **Publishing status** as **Testing** for staging.
4. Under **Test users**, click **Add users**, enter every Google account that
   will perform the live login, and click **Save**.

For this app's identity-only scopes (`openid`, `email`, `profile`), the test
user allow-list and warning behavior are less restrictive than for sensitive
Google API scopes. Still add test users explicitly so the staging procedure
also works if scopes are expanded later. Do not click **Publish app** until a
production domain, privacy policy, and review decision are ready.

### 2.4 Data Access: request only identity scopes

1. Open **Google Auth Platform → Data Access**.
2. Click **Add or remove scopes**.
3. Select or enter only these OpenID Connect identity scopes:
   - `openid`
   - `email`
   - `profile`
4. Click **Update**, then **Save**.

Do not add Drive, Calendar, Gmail, or other sensitive/restricted scopes for
login. A later feature that needs them must update the consent-screen
justification, privacy policy, security review, and verification plan.

### 2.5 Clients: create the web OAuth client

1. Open **Google Auth Platform → Clients**.
2. Click **Create client**.
3. Set **Application type** to **Web application**.
4. Set the client name to something explicit, such as
   `ai-saas-staging-localhost-3000`.
5. Add the exact JavaScript origin and redirect URI from the next section.
6. Click **Create**.
7. Copy the **Client ID** immediately. Copy the **Client secret** immediately
   as well: Google may show/download the secret only at creation time. Store it
   in `.env.local` or a secret manager, never in browser code or Git.

The web client is a server-side OAuth client in this project because Better
Auth performs the authorization-code exchange. The browser only starts the
redirect flow; it must never receive `GOOGLE_CLIENT_SECRET`.

Google's official [OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server),
[consent-screen setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid),
[audience guidance](https://support.google.com/cloud/answer/15549945), and
[client management guide](https://support.google.com/cloud/answer/15549257)
describe the corresponding console screens.

## 3. Register exact redirect URIs

Add the following to the Web application client. The OAuth callback is the API
route, not the `/auth/callback` explanatory UI page.

| Environment | Authorized JavaScript origin | Authorized redirect URI |
|---|---|---|
| Live local test | `http://localhost:3000` | `http://localhost:3000/api/auth/callback/google` |
| Production | `https://YOUR_DOMAIN` | `https://YOUR_DOMAIN/api/auth/callback/google` |

The redirect URI must match exactly. Register `localhost`, not `127.0.0.1`,
and do not add a trailing slash. Keep the same origin in Google Cloud, the
browser address bar, and `BETTER_AUTH_URL`.

## 4. Create the runtime environment

The repository includes a repeatable setup command. Keep the Google client
values in `apps/web/.env.local`, authenticate the Neon CLI once, then run this
from the repository root:

```bash
pnpm web:setup-auth -- --link-neon --neon-branch stage2 --app-env staging
```

The command links the selected Neon branch, imports its pooled `DATABASE_URL`,
reuses an existing `BETTER_AUTH_SECRET` or generates one, sets the localhost
callback configuration, and validates the Google values. It never prints
secret values, preserves unrelated values already in the file, and does not
change the database.

The resulting values in `apps/web/.env.local` include:

```text
APP_ENV=staging
DATABASE_URL=<Neon production-or-staging connection string>
BETTER_AUTH_URL=http://localhost:3000
BETTER_AUTH_SECRET=<long random server-only secret>
GOOGLE_CLIENT_ID=<web-client-id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<server-only-client-secret>
NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
```

When the web app runs through Docker Compose, copy the same server-side values
to the ignored root `.env`. Docker does not automatically read
`apps/web/.env.local`. Start the stack from the repository root with:

```bash
pnpm docker:local
```

This command explicitly loads the root `.env`, rebuilds the web image, and
force-recreates the containers. Without recreating the web container, a
previously empty Google configuration remains in its process environment and
the login page intentionally shows the setup guide instead of the Google
button.

To use a different Neon project or branch, pass `--neon-project-id` and
`--neon-branch`. The default project is the repository's linked `ai_saas`
project and the default branch is `production`.

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

Install dependencies and use the environment-specific migration path. Local
OAuth development uses disposable Docker PostgreSQL:

```bash
pnpm install
pnpm docker:local
```

For a Neon staging OAuth check, use the reviewed migration gate instead of a
raw package migration command:

```bash
NEON_BRANCH=stage2 pnpm run db:verify:stage -- --from-file "$PWD/.env.staging"
NEON_BRANCH=stage2 pnpm run db:plan:stage -- --from-file "$PWD/.env.staging"
CONFIRM_STAGING_DB=staging NEON_BRANCH=stage2 \
  pnpm run db:migrate:stage -- --from-file "$PWD/.env.staging"
```

The Drizzle config still reads `apps/web/.env.local` for local-only commands.
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
pnpm --filter ai-saas-foundation-web dev
```

Open [http://localhost:3000/login](http://localhost:3000/login). With live
configuration, the only action must say **Continue with Google**. Without live
configuration, the page must show a Google OAuth setup notice and link to this
guide; it must not expose member/admin demo buttons.

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

For the complete local Docker incident runbook, including the port-conflict
and build-time `NEXT_PUBLIC_*` failure modes, see
[Google OAuth local troubleshooting](../troubleshooting/google-oauth-local.md).

| Symptom | Check |
|---|---|
| `redirect_uri_mismatch` | Browser origin, port, path, scheme, and trailing slash match the Google client exactly. |
| `access_denied` or test-user warning | Add the account under Google Cloud **Audience → Test users** or publish the app when ready. |
| Google setup notice remains | `APP_ENV`, `BETTER_AUTH_URL`, database, Google client values, and `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true` were not loaded by the web process. |
| Google setup notice remains in Docker | Put the values in the root `.env` and run `pnpm docker:local`; changing `apps/web/.env.local` alone does not update an existing container. |
| `auth_not_configured` | The server intentionally failed closed because one required live-auth value is missing. Restart after editing `.env.local`. |
| `/admin` redirects to login | The Google user exists but `app_user.role` is not `admin`/`super_admin`, or the session predates the role change. |
| `invalid_client` | Client ID/secret belong to a different Google Cloud project or environment. Rotate the secret in the deployment secret store. |
| OAuth works, but DB migration fails | For local Docker, restart with `pnpm docker:local`; for Neon staging, rerun `db:verify:stage` and stop on any incompatible migration history instead of editing the history table. |

## 10. Production handoff

Before production, create a separate HTTPS OAuth client and replace every
local URI with the production domain. Verify the domain, provide a public
homepage/privacy policy if required, review requested scopes, and move the
Google app out of Testing only after the test flow is stable. Keep staging and
production client secrets separate. Google's [production readiness guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
and [policy compliance guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/policy-compliance)
describe the publishing and verification requirements.

For credential-free development, remove the live values and use the setup
notice only. Automated contract tests may use an `APP_ENV=test` fixture, but
that route is not exposed as a user-facing login and is not evidence of a
successful Google OAuth exchange.
