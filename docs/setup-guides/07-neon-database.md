---
id: database-neon
category: DATABASE
title: Neon PostgreSQL
summary: Link the cloud production branch, inject connection variables safely, and verify the database without exposing credentials.
---

# Neon PostgreSQL

Neon is the cloud database baseline for the foundation. Local Docker remains
the disposable development path; the linked `production` branch is the
durable cloud path.

## 1. Authenticate from a supported browser

Run the CLI from a normal local terminal and finish the OAuth flow in the
existing Chrome or Safari profile. Do not use an embedded browser or commit a
token.

```bash
npm install --global neon@latest
neon auth
```

## 2. Install project tooling

Install the Neon agent skills and MCP configuration only on a trusted
developer machine. The MCP command creates an account-scoped credential in
local agent configuration; rotate or revoke it if the machine is shared.

```bash
neon skills -y
neon mcp -y
```

## 3. Link the production branch

The current project is `ai_saas` (`lucky-boat-01406333`). Replace the project
ID when setting up a derivative project.

```bash
neon link --project-id lucky-boat-01406333 --branch production -y
```

This creates the ignored `.neon` context and pulls `DATABASE_URL`,
`DATABASE_URL_UNPOOLED`, and `NEON_BRANCH` into the ignored `.env.local` file.

## 4. Apply the repository policy

The committed `neon.ts` deliberately starts with an empty policy so existing
Neon project defaults are preserved. Preview first, then apply.

```bash
neon config init
neon config plan
neon deploy
```

## 5. Verify the connection

Run a read-only query against the linked branch.

```bash
neon status --output json
neon psql production -- -c "select current_database(), current_schema(), current_setting('server_version');"
```

Expected output includes database `neondb`, schema `public`, and a current
Neon PostgreSQL version. Never print or paste the full connection string.

## 6. Select the deployment mode

The local `free-portfolio` profile intentionally uses disposable local
storage so a fresh clone can run without cloud credentials. Cloud deployment
injects the ignored Neon variables through the host secret manager. Neon
provisioning does not enable payment or model-provider secrets and does not
replace the integration validators.
