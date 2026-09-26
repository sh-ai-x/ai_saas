---
id: getting-started
category: START HERE
title: Local foundation
summary: Run the complete process or Docker vertical slice before enabling external providers.
---
# Local foundation

Run the web console, API, durable run, admin audit, and mock payment path with
no cloud account. Choose either process mode or the full Docker mode. The
browser login remains Google-only; without OAuth credentials the login page
shows setup instructions instead of a mock member/admin login.

## 1. Process mode

Generate the secret in the shell, start the Python composition root, and keep
the terminal open.

```bash
export APP_SECRET_KEY="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --locked python -m foundation.server --env-file config/profiles/free-portfolio.example.env --profile free-portfolio
```

In another terminal, start the Next.js console:

```bash
pnpm install
pnpm --filter ai-saas-foundation-web dev
# open http://localhost:3000
```

## 2. Full Docker mode

The production-shaped Compose file starts PostgreSQL, the Foundation API, a
Drizzle migration job, and the Next.js web image. It does not require Vercel,
Neon, Google, Toss, or Lemon Squeezy credentials in its default local mode.

```bash
cp .env.local.example .env
pnpm docker:local
```

The first available slot uses web `3100`, API `8180`, and PostgreSQL `55433`;
other worktrees receive the next free `+10` block, shown in the Compose output.
Internal service ports remain `3000`, `8080`, and `5432`. The local override
runs Next.js in development mode, which keeps rebuilds practical on an 8 GB
laptop. Stop the stack with `pnpm docker:local down`; use
`pnpm docker:local down --volumes` only when disposable local data should be
removed.

The local Compose PostgreSQL service uses trust authentication and does not
require `POSTGRES_PASSWORD`. For a real Google login, fill the server-only
Better Auth and Google values in the ignored root `.env`; the Docker service
does not automatically load `apps/web/.env.local`. The `docker:local` command
always reads the root `.env`, rebuilds, and force-recreates the stack so
changes to OAuth or database settings reach the containers. If
`APP_SECRET_KEY` is blank, it generates an ephemeral value for that run.

## 3. Verify the contract

Use the health endpoint, proposal-review contract, audited admin change, and
mock payment before introducing external credentials. Validate real account
creation and login through the Google OAuth guide after configuring the
provider.

```bash
curl http://localhost:8180/healthz
uv run --locked python -m foundation.contract_check
bash scripts/verify-local.sh
```
