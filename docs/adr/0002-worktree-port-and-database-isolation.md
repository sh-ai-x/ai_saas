# ADR-0002: Isolate worktree ports and database targets

- Status: accepted
- Date: 2026-09-21
- Scope: local Docker execution and Neon environment boundaries

## Decision

Every Git worktree gets its own Docker Compose project, host-port block, and
PostgreSQL volume. The Compose service ports remain stable inside the private
network: web `3000`, Foundation `8080`, and PostgreSQL `5432`. Only host ports
are allocated per worktree because changing internal service contracts adds
complexity without improving isolation.

The local runner derives a stable slot from the worktree branch, probes for a
free block, and reuses the existing block for an already-running Compose
project. `DOCKER_LOCAL_SLOT=0..39` is the explicit override for CI or a manual
collision resolution. The default block is:

| Service | Host-port formula | Container port |
|---|---:|---:|
| Web | `3100 + slot * 10` | `3000` |
| Foundation API | `8180 + slot * 10` | `8080` |
| PostgreSQL | `55433 + slot * 10` | `5432` |

The Compose project name is derived from the sanitized Git branch. Compose
therefore prefixes each worktree's network and volumes independently. A local
run always points the web migration and application database at the local
Compose PostgreSQL service unless `ALLOW_REMOTE_DATABASE=true` is explicitly
provided for a diagnostic run.

Neon is reserved for cloud-like environments:

| Environment | Database target | Lifetime | Data policy |
|---|---|---|---|
| `local` | worktree-local Docker PostgreSQL | disposable/persistent per local volume | synthetic seed data |
| `preview` | Neon branch per PR/worktree | ephemeral; delete on close | synthetic or masked data |
| `staging` | protected long-lived Neon branch | shared release candidate | masked/non-production data |
| `production` | protected Neon `production` branch | durable | real data |

Neon connection strings are injected by the environment or CI secret store;
they are never copied into a worktree's committed files. Drizzle migrations
run once as an environment release job: `web-migrate` locally, a preview or
staging migration job in CI, and an explicitly approved production release
job.

## Rationale

Neon branches have unique connection strings and are isolated from each other,
which makes a branch-per-PR or branch-per-developer workflow a natural cloud
analogue to the local worktree model. A protected production branch also
prevents accidental reset/deletion, while child branches receive separate
credentials. If production contains PII, staging and preview must derive from
an anonymized or synthetic-data branch rather than exposing production data.

## Consequences

Positive consequences:

- Running multiple worktrees no longer competes for `3000`, `8080`, or `5432`.
- `docker compose down` for one project cannot remove another worktree's
  PostgreSQL volume when the project name is preserved.
- Local development cannot silently run migrations against Neon.
- Preview data and credentials are isolated from staging and production.

Trade-offs:

- Port slots and Neon preview branches need lifecycle cleanup.
- A local worktree is not production infrastructure; production isolation
  remains a deployment and cloud policy concern.
- Neon branch creation, secret injection, and deletion belong in CI rather
  than in the untrusted local Docker command.

## Operational rules

1. Do not put `DATABASE_URL`, Neon credentials, or production secrets in Git.
2. Use `pnpm docker:local down` for one worktree; use
   `pnpm docker:local down --volumes` only when its local data is disposable.
3. Do not use `production` credentials for local, preview, or staging.
4. Do not run production migrations from a developer worktree.
5. Delete preview branches and release unused local volumes when the worktree
   is retired.
