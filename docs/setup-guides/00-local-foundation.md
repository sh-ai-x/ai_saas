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
cp .env.docker.example .env
export APP_SECRET_KEY="$(openssl rand -base64 32)"
docker compose -f docker/prod/compose.yaml up --build
```

Open [http://localhost:3000](http://localhost:3000). The API is available at
[http://localhost:8080/healthz](http://localhost:8080/healthz). Stop the
stack with `docker compose -f docker/prod/compose.yaml down`; add `-v` only
when disposable local data should be removed.

## 3. Verify the contract

Use the health endpoint, bounded run, audited admin change, and mock payment
before introducing external credentials. Validate real account creation and
login through the Google OAuth guide after configuring the provider.

```bash
curl http://localhost:8080/healthz
uv run --locked python -m foundation.contract_check
bash scripts/verify-local.sh
```
