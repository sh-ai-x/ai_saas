# Local foundation

## Goal

Run the web console, API, durable run, admin audit, and mock payment path with
no cloud account or Docker daemon.

## Start

```bash
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m foundation.server \
  --env-file config/profiles/free-portfolio.example.env \
  --profile free-portfolio
```

In another terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. The browser uses the same-origin proxy and the
API uses SQLite state under `/tmp` by default.

## Expected checks

```bash
curl http://127.0.0.1:8080/healthz
python3 -m foundation.contract_check
bash scripts/verify-local.sh
```

Use this mode as the baseline for every later provider change. It proves the
application contract without spending money or sending user prompts outside
the machine.
