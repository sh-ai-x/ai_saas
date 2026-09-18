# web-console

This is the local Next.js 15 App Router console for the AI SaaS foundation.
It is intentionally provider-free: browser requests go through the same-origin
`/api/foundation/*` Route Handler proxy to the local Python composition root.
The UI exercises mock Google auth, tenant-scoped admin operations, mock payment
webhooks, durable runs, and SSE replay without cloud credentials.

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

Open http://127.0.0.1:3000. Set `FOUNDATION_API_URL` when the API is not at
`http://127.0.0.1:8080`.

```bash
FOUNDATION_API_URL=http://127.0.0.1:8080 npm run dev
```

The production build is local-only and does not require Vercel, Neon, Stripe,
Toss, Lemon Squeezy, or a running Docker daemon:

```bash
npm run build
npm run start
```

The left sidebar contains category guides for local startup, Google OAuth,
Toss/Lemon Squeezy sandbox payments, OpenAI/Anthropic/Gemini Agent providers,
verification, and operations. Each guide is imported at build time from the
Markdown files in `apps/web/content/guides/*.md`, displayed as a read-only
Markdown editor with line numbers, and connected to the live console actions.
The same source is mirrored as canonical documentation under
`docs/setup-guides/`.
