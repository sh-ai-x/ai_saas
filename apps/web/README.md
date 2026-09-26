# web-console

This is the local Next.js 15 App Router console for the AI SaaS foundation.
Browser requests go through the same-origin `/api/foundation/*` Route Handler
proxy to the local Python composition root. Google OAuth is the only
user-facing sign-up/sign-in path: the first Google authorization creates a
regular account and existing accounts sign in. Admin access is decided by the
persisted `app_user.role`, never by a separate admin login. Mock payment
webhooks, durable runs, and SSE replay remain available for local contract
testing without external payment credentials.

## Run locally

Start the foundation API from the repository root first:

```bash
export APP_SECRET_KEY="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --locked python -m foundation.server \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
```

Then, from the repository root, install and start the web console:

```bash
pnpm install
pnpm --filter ai-saas-foundation-web dev
```

Open http://localhost:3000 for the public landing page. The user workspace is
at `/app`, the separate admin console is at `/admin`, and setup guides are at
`/guides`. Set `FOUNDATION_API_URL` when the API is not at
`http://localhost:8080`.

```bash
FOUNDATION_API_URL=http://localhost:8080 pnpm --filter ai-saas-foundation-web dev
```

## Run the web console as a Docker image

From the repository root, the production-shaped Compose stack starts the web
image, Foundation API, PostgreSQL companion, and Drizzle migration job:

```bash
cp .env.local.example .env.local
pnpm docker:local
```

The Docker browser uses `http://localhost:3100`; the local Docker override runs
Next.js in development mode so an 8 GB laptop does not need a standalone trace
build on each local rebuild. The Next.js server reaches the
API at `http://foundation:8080` inside the Compose network. The `web-migrate`
one-shot service applies the committed Drizzle migrations before the web
container starts. The default Docker profile is local/demo mode with mock
payments. Local Compose PostgreSQL uses trust authentication and does not
require `POSTGRES_PASSWORD`. For live Google login, fill the server-only
Better Auth and Google values in the ignored root `.env.local`; `apps/web/.env.local`
is used by process-mode commands, not automatically by Docker Compose.
`pnpm docker:local` explicitly loads the root `.env`, rebuilds the local images, and
force-recreates the containers so changed OAuth values are applied.

The production build is local-only and does not require Vercel, Neon, Stripe,
Toss, Lemon Squeezy, or a running Docker daemon:

```bash
pnpm --filter ai-saas-foundation-web build
pnpm --filter ai-saas-foundation-web start
```

Run the Jest contract and adapter test suite without provider credentials:

```bash
pnpm --filter ai-saas-foundation-web test
pnpm --filter ai-saas-foundation-web test:watch
pnpm --filter ai-saas-foundation-web test:all
pnpm web:e2e
```

The tests cover Google auth contracts, exclusive billing-mode publishing, admin authorization,
checkout rejection for the inactive mode, pricing validation, provider
conflicts, and mock/Toss/Lemon Squeezy adapter handoffs. `pnpm web:e2e`
starts a disposable Next.js server on port `3015` and exercises the real HTTP
routes for Google fail-closed behavior, test-only signup/login/logout, session
revocation, member/admin authorization, subscription policy transitions,
checkout validation, sandbox provider selection, and Foundation API outage
handling. It uses the explicit `APP_ENV=test` local seed profile and never
grants live entitlements. A real Google account callback and provider-hosted
payment page remain manual staging smoke checks because they require external
browser credentials and must never be automated with a stored user account.

The `/guides` route contains the category sidebar for local startup, Google
OAuth, separate Toss and Lemon Squeezy sandbox payment guides,
proposal review, verification, and operations. Each
guide is imported at build time from the Markdown files in
`apps/web/content/guides/*.md`, displayed as a read-only Markdown editor with
line numbers, and rendered below as a GitHub-Flavored Markdown preview with
headings, lists, tables, links, blockquotes, and fenced code. The database group
contains the Neon PostgreSQL setup guide, including safe `.env.staging`/`.neon`
handling and read-only connection verification. The same source is mirrored as
canonical documentation under `docs/setup-guides/`. Pricing is managed from
`/admin/pricing` through Drizzle/Neon tables and supports one-time, monthly,
and yearly options. Provider settings are managed from `/admin/payments`; the
local fallback is explicitly labeled and production fails closed without
`DATABASE_URL`.
