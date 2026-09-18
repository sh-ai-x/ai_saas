---
id: getting-started
category: START HERE
title: Local foundation
summary: Run the complete no-credential vertical slice before enabling external providers.
---
# Local foundation

Run the web console, API, durable run, admin audit, and mock payment path with
no cloud account or Docker daemon.

## 1. Start the API

Generate the secret in the shell, start the Python composition root, and keep
the terminal open.

```bash
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m foundation.server --env-file config/profiles/free-portfolio.example.env --profile free-portfolio
```

## 2. Start the web console

The Next.js app proxies same-origin requests to the API.

```bash
cd apps/web
npm install
npm run dev
# open http://127.0.0.1:3000
```

## 3. Verify the contract

Use the health endpoint, local mock login, bounded run, audited admin change,
and mock payment before introducing external credentials.

```bash
curl http://127.0.0.1:8080/healthz
python3 -m foundation.contract_check
bash scripts/verify-local.sh
```
