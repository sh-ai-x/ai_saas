---
id: database-neon
category: DATABASE
title: Neon PostgreSQL
summary: Select a Neon environment, inject connection variables safely, and verify the database without exposing credentials.
---

# Neon PostgreSQL

Neon is the cloud database baseline for the foundation. Local Docker remains
the disposable development path; named Neon `stage2` and `production` branches
are durable cloud environments.

## 1. Authenticate from a supported browser

Run the CLI from a normal local terminal and finish the OAuth flow in the
existing Chrome or Safari profile. Do not use an embedded browser or commit a
token.

```bash
pnpm add --global neon@latest
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

For the web app, run the setup command after linking. It copies the Neon URL
into `apps/web/.env.local`, generates the Better Auth secret if needed, and
validates Google OAuth values. It does not apply a cloud migration:

```bash
pnpm web:setup-auth -- --neon-branch stage2 --app-env staging
```

Add `--link-neon` when the branch has not been linked yet.
Run the staging `verify → plan → apply → verify` gate below for database
changes; do not call the web package's raw migration command against Neon.

## 4. Apply the repository policy

The committed `neon.ts` deliberately starts with an empty policy so existing
Neon project defaults are preserved. Preview first, then apply.

```bash
neon config init
neon config plan
neon deploy
```

## 5. Verify the connection

Run a read-only query against the linked branch. Use the pooled URL for normal
application traffic and the unpooled URL for migrations or administrative
operations when the deployment platform requires that distinction.

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

## 7. Verify and migrate the staging branch

Keep `DATABASE_URL` pooled for application traffic and use
`DATABASE_URL_UNPOOLED` for Drizzle migrations:

```bash
NEON_BRANCH=stage2 pnpm run db:verify:stage -- --from-file "$PWD/.env.stage"
NEON_BRANCH=stage2 pnpm run db:plan:stage -- --from-file "$PWD/.env.stage"
CONFIRM_STAGING_DB=staging NEON_BRANCH=stage2 \
  pnpm run db:migrate:stage -- --from-file "$PWD/.env.stage"
```

Success requires current migration history and the final
`migration release: APPLY PASS` message. Stop on incompatible history; never
edit or delete `drizzle.__drizzle_migrations` manually.
