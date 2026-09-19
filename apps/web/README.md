# web-console

This is the local Next.js 15 App Router console for the AI SaaS foundation.
It is intentionally provider-free: browser requests go through the same-origin
`/api/foundation/*` Route Handler proxy to the local Python composition root.
The UI exercises mock Google auth, tenant-scoped admin operations, mock payment
webhooks, durable runs, and SSE replay without cloud credentials. When a
sandbox provider is configured, Toss is handed to its browser SDK with
server-created order context, while Lemon Squeezy opens its hosted checkout;
credits are still granted only by the signed provider event path.

## Run locally

Start the foundation API from the repository root first:

```bash
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m foundation.server \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
```

Then start the web console in this directory:

```bash
npm install
npm run dev
```

Open http://localhost:3000 for the public landing page. The user workspace is
at `/app`, the separate admin console is at `/admin`, and setup guides are at
`/guides`. Set `FOUNDATION_API_URL` when the API is not at
`http://localhost:8080`.

```bash
FOUNDATION_API_URL=http://localhost:8080 npm run dev
```

## Run the web console as a Docker image

From the repository root, the production-shaped Compose stack starts the web
image, Foundation API, PostgreSQL companion, and Drizzle migration job:

```bash
cp .env.docker.example .env
export APP_SECRET_KEY="$(openssl rand -base64 32)"
docker compose -f docker/prod/compose.yaml up --build
```

The browser uses `http://localhost:3000`; the Next.js server reaches the API
at `http://foundation:8080` inside the Compose network. The `web-migrate`
one-shot service applies the committed Drizzle migrations before the web
container starts. The default Docker profile is local/demo mode with mock
payments. Use `WEB_DATABASE_URL` and server-only environment values from a
secret manager for staging or production.

The production build is local-only and does not require Vercel, Neon, Stripe,
Toss, Lemon Squeezy, or a running Docker daemon:

```bash
npm run build
npm run start
```

Run the contract and adapter test suite without provider credentials:

```bash
npm run test
npm run test:all
```

The tests cover exclusive billing-mode publishing, admin authorization,
checkout rejection for the inactive mode, pricing validation, provider
conflicts, and mock/Toss/Lemon Squeezy adapter handoffs. They use the explicit
`APP_ENV=test` local seed profile and never grant live entitlements.

The `/guides` route contains the category sidebar for local startup, Google
OAuth, separate Toss and Lemon Squeezy sandbox payment guides,
OpenAI/Anthropic/Gemini Agent providers, verification, and operations. Each
guide is imported at build time from the Markdown files in
`apps/web/content/guides/*.md`, displayed as a read-only Markdown editor with
line numbers, and linked back to the operator console. The database group
contains the Neon PostgreSQL setup guide, including safe `.env.local`/`.neon`
handling and read-only connection verification. The same source is mirrored as
canonical documentation under `docs/setup-guides/`. Pricing is managed from
`/admin/pricing` through Drizzle/Neon tables and supports one-time, monthly,
and yearly options. Provider settings are managed from `/admin/payments`; the
local fallback is explicitly labeled and production fails closed without
`DATABASE_URL`.
