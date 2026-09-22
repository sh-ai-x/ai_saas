# Neon database setup

Neon PostgreSQL is the cloud database baseline for the AI SaaS foundation.
The repository keeps the first runtime inexpensive: local Docker can still
use its disposable PostgreSQL companion, while the linked Neon `production`
branch is the durable cloud database.

## Current project

- Project: `ai_saas`
- Project ID: `lucky-boat-01406333`
- Organization: `SH` (`org-delicate-bar-61352806`)
- Branch: `production`
- Region: `aws-ap-southeast-1`
- PostgreSQL: `18.6`

The project ID supplied during the initial setup (`silent-pine-12564595`) was
not present in the authenticated account. The account contained one project
named `ai_saas`, so the setup links that project explicitly.

## First-time setup

Run these commands from the repository root in a normal terminal:

```bash
npm install --global neon@latest
neon auth
neon skills -y
neon mcp -y
neon link --project-id lucky-boat-01406333 --branch production -y
neon config init
neon deploy
```

`neon link` creates the ignored `.neon` context file and pulls
`DATABASE_URL`, `DATABASE_URL_UNPOOLED`, and `NEON_BRANCH` into the ignored
`.env.local` file. Never commit `.env.local`, Neon credentials, or an MCP API
key.

The committed `neon.ts` is intentionally minimal:

```ts
import { defineConfig } from "@neon/config/v1";

export default defineConfig({});
```

This keeps the first deployment at Neon’s existing project defaults. Add a
branch policy only when the requirement is explicit and verify it with
`neon config plan` before applying it.

## Verify the connection

```bash
neon status --output json
neon config plan
neon psql production -- -c \
  "select current_database() as database, current_schema() as schema, current_setting('server_version') as postgres_version;"
```

The expected result is the `production` branch, database `neondb`, schema
`public`, and the current Neon PostgreSQL version.

## Local versus cloud profiles

The `free-portfolio` profile keeps a disposable local database URL so a fresh
clone can run without cloud credentials. For cloud-backed operation, load the
ignored `.env.local` values or inject equivalent variables through the deploy
platform. The application must still pass its normal configuration validation;
Neon provisioning alone does not authorize provider secrets or production
payment traffic.

Use the unpooled URL for migrations or administrative operations and the
pooled URL (`DATABASE_URL`) for application traffic when the deployment host
benefits from connection pooling. Keep migrations serialized and run them
against the linked `production` branch only from an approved release step.

For a Docker web runtime against a preview or staging branch, copy the two
connection variables and runtime secrets into the ignored Neon Docker env
file:

```bash
cp .env.neon.example .env.neon
pnpm docker:neon
```

`docker:neon` does not start the bundled PostgreSQL service. It sends
`DATABASE_URL` to the web runtime and `DATABASE_URL_UNPOOLED` only to the
one-shot Drizzle migration container. Use `pnpm docker:local` when the target
should remain the isolated PostgreSQL volume for the current worktree.

## Troubleshooting

- `Project not found`: authenticate with the account that owns the project and
  list projects with `neon projects list --org-id <org-id>`.
- Browser callback refused: run `neon auth` in a normal local terminal and
  complete the flow in the existing Chrome/Safari profile; do not use an
  embedded browser.
- Keyring command hangs: unlock the macOS login keychain, then retry. File
  storage is also supported by running `neon auth` without `--keyring`.
- `neon config plan` reports drift: inspect the plan before deploying; do not
  apply an unreviewed branch or compute-policy change.
