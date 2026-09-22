# Deployment Spec — Proposal-to-Verified-Change Agent + Foundation

> Companion to [`implementation-status.md`](./implementation-status.md). Defines the three runtime profiles, host port strategy, and the scripts that drive them.
>
> This is the Local Lite + offline slice; the proposal rules R1–R14 ([`rules/proposal-to-verified-change-agent.md`](../../../rules/proposal-to-verified-change-agent.md)) still apply.

## 1. Topology (today)

The agent **adds no new HTTP services**. It is a Python library that runs inside the foundation API (`services/control_api`) and uses the same SQLite state. Adding a separate `agent` container in Local Lite would break rule R11 (at most two long-lived processes) and rule R12 (nginx edge in production only).

```
                  ┌─────────────────────────────────────────────────────┐
                  │ Local Lite (8GB laptop)                             │
                  │                                                     │
   browser ──▶ nginx :8080 ──▶ foundation :8000 ──▶ SQLite (./data)    │
                            (control_api + workflow + sandbox inline)  │
                  │                                                     │
                  │ Long-lived processes: nginx, foundation = 2         │
                  └─────────────────────────────────────────────────────┘
                  ┌─────────────────────────────────────────────────────┐
                  │ Production MSA (separate deployable boundaries)     │
                  │                                                     │
   browser ──▶ nginx :443 ──▶ foundation-api :8080 ──▶ PostgreSQL       │
                  │                  │                                 │
                  │                  ├─▶ agent-orchestrator :8081     │
                  │                  ├─▶ sandbox-worker   :8082        │
                  │                  └─▶ delivery-gateway :8083        │
                  │                                                     │
                  │ Long-lived processes: 5 (nginx + 4 service pods)    │
                  └─────────────────────────────────────────────────────┘
```

## 2. Host port strategy

### 2.1 Why slot-based allocation, not fixed ports

Multiple worktrees run in parallel during development. A fixed `3000` collides with Next.js, Stripe CLI, debuggers, and the previous worktree's container. The existing script `scripts/docker-local.sh` derives a stable **slot** per branch and assigns a contiguous block of three host ports (web + foundation + postgres). This is collision-checked against `lsof`.

### 2.2 The slot table

Each profile owns a numeric range. Slots are integers `0–39`. The branch name hashes into a deterministic seed slot; collisions probe forward to the next free slot.

| Profile | Web host port | Foundation host port | Postgres host port | Internal ports |
|---|---:|---:|---:|---|
| `docker:local`  (slot `S`) | `3100 + 10·S` | `8180 + 10·S` | `55433 + 10·S` | web 3000, foundation 8080, postgres 5432 |
| `docker:stage`  (slot `S`) | `3200 + 10·S` | `8280 + 10·S` | `56433 + 10·S` | web 3000, foundation 8080, postgres 5432 |
| `docker:prod`   | n/a (nginx owns 443) | n/a (private network only) | n/a (managed Postgres) | web 3000, foundation 8080, postgres 5432 |

Slot math guarantees **non-overlapping ranges across profiles** because the prefixes differ (`31xx` vs `32xx`, `81xx` vs `82xx`, `554xx` vs `564xx`). Two worktrees on the same profile still avoid each other because the slot is per-branch.

### 2.3 Why NOT 3000 / 3019

`3000` collides with:

- Next.js dev server when the container is down
- Stripe CLI / ngrok / VS Code Code-Server / Jupyter
- The previous worktree's container if `docker:local:down` was skipped

`3019` is worse — it does not match any of the three known ranges (`31xx`, `32xx`, `554xx`). The slot table keeps every host port inside a discoverable `3100–3190 / 3200–3290 / 55433–55443 / 56433–56443` window. Anything outside is a typo or a forgotten manual override.

**Recommendation:** stop binding host ports `3000` and `3019` directly. Use the slot table:

```bash
pnpm docker:local          # slot 0 → web :3100, foundation :8180, postgres :55433
pnpm docker:local:status   # see assigned ports
```

If you must bind to `3000` (e.g., a public demo URL), use the `docker:prod` profile — it terminates at nginx :443 and the web container stays on the private network.

### 2.4 nginx in Local Lite — port 8080, not 80

`infra/nginx/local-lite.conf` listens on **`8080`**, not `80`, because binding `80` requires root and conflicts with macOS AirPlay on port 5000/7000. Production nginx owns `443` (TLS) and `80` (HTTP→HTTPS redirect).

## 3. The three profiles

### 3.1 `docker:local` — developer loop (already shipped)

```bash
pnpm docker:local
pnpm docker:local:status
pnpm docker:local:down
pnpm docker:local:purge   # also drops volumes
```

- Compose: `docker/prod/compose.yaml` + `docker/local/compose.yaml` (Next.js `development` target, hot reload)
- DB: local Postgres inside the stack
- Provider mode: fake (`infra/profiles/local-lite/profile.yaml: provider_mode: fake`)
- Sandbox: deterministic (no real shell)
- Long-lived: 2 (nginx, foundation)
- Host ports: slot-derived (`3100`, `8180`, `55433` for slot 0)
- Override via `DOCKER_LOCAL_SLOT=N` or `WEB_PORT=…` / `FOUNDATION_PORT=…` / `POSTGRES_PORT=…`

### 3.2 `docker:stage` — staging cluster with cloud DB (NEW)

This profile reuses the production-shape image (Next.js `runner`, foundation `prod`) but points the web at a **Neon pooled URL** and exposes a separate slot range so it cannot collide with a developer's local stack.

```bash
pnpm docker:stage
pnpm docker:stage:status
pnpm docker:stage:down
pnpm docker:stage:purge
```

- Compose: `docker/prod/compose.yaml` + `docker/stage/compose.yaml`
- DB: Neon pooled URL (`DATABASE_URL`), direct/unpooled URL for migrations (`DATABASE_URL_UNPOOLED`)
- Provider mode: fake (no live provider key required by default)
- Sandbox: deterministic
- Host ports: `3200` (web), `8280` (foundation), `56433` (postgres optional) — slot-derived
- `BETTER_AUTH_SECRET` and `APP_SECRET_KEY` are required (no ephemeral generation in stage)
- `MOCK_PAYMENTS_ENABLED=true` keeps Toss out of the staging checkout flow unless `PAYMENT_SANDBOX=true`

Required env (`stage` only):

```env
DATABASE_URL=postgresql://...pooler...neon.../neondb?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://...neon.../neondb?sslmode=require
BETTER_AUTH_SECRET=<32-byte hex>
APP_SECRET_KEY=<32-byte hex>
```

If either `DATABASE_URL` is missing the script exits with a non-zero status — staging never silently falls back to the local container DB.

### 3.3 `docker:prod` — production cluster

The `docker:prod` profile does **not** bind host ports for the application services. Only nginx is exposed:

```bash
# Production deploy uses the image registry, not docker:local. The compose
# file is here so `docker compose config` can validate it in CI.
docker compose -f docker/prod/compose.yaml config
```

- Compose: `docker/prod/compose.yaml` only (no override)
- DB: managed Postgres / Neon prod branch (private network)
- Provider mode: real (`OPENAI_API_KEY`, `LANGCHAIN_API_KEY` required)
- Sandbox: real container worker (PR #32 scope)
- Long-lived: 5 (nginx, foundation-api, agent-orchestrator, sandbox-worker, delivery-gateway)
- Host ports: nginx owns `443` (TLS) and `80` (HTTP→HTTPS redirect); all app services stay on the private network
- TLS: terminate at nginx; certs mounted as a read-only volume; never baked into the image

### 3.4 Profile decision matrix

| Need | Profile |
|---|---|
| Edit Next.js code with hot reload | `docker:local` |
| Test foundation API + workflow + fake provider | `docker:local` |
| Reproduce a cloud-only Postgres behavior | `docker:stage` |
| Verify migration + Drizzle against Neon | `docker:stage` |
| Stage demo for a stakeholder | `docker:stage` |
| Production deployment | `docker:prod` (image registry + K8s / Nomad / Fargate) |
| CI / lint that only needs to validate compose | `docker compose -f docker/prod/compose.yaml config` |

## 4. Adding `docker:stage` to the repository

Three new files plus one `package.json` entry:

1. `docker/stage/compose.yaml` — override that pins `target: runner`, points at Neon, uses the stage slot prefix, and rejects the local DB.
2. `scripts/docker-stage.sh` — slot allocator for the `3200/8280/56433` range, env-file gate (`DATABASE_URL` required), and the same `lsof` probe as `docker-local.sh`.
3. `package.json` — add `docker:stage`, `docker:stage:down`, `docker:stage:purge`.

## 5. Recommendations for the user's "3000 and 3019" setup

| Issue | Fix |
|---|---|
| `3000` collides with Next.js dev and other tooling | Stop binding `3000` on host. Use `pnpm docker:local` which assigns a slot-derived port (e.g. `3100`, `3110`, …). The web container still listens on `3000` internally |
| `3019` is outside the slot range and undocumented | Replace with the next slot. Pick `pnpm docker:local` slot 0 → `3100`; if you need both web and a debug port, use `3200` (stage range) for the second one |
| No isolation between two parallel worktrees | Each worktree hashes its branch name into a deterministic slot; slots 0–39 give 40 parallel stacks per profile |
| Forgetting to `docker:local:down` blocks the next slot | `pnpm docker:local:status` shows assigned ports; the slot allocator probes forward on collision so a stale stack never blocks a new one |
| Want `3000` for a public demo URL | Use `docker:prod` (nginx :443 → web :3000 private) — never bind `3000` directly to a public interface |
| Need TLS locally | Not supported in Local Lite by rule R11 (no Nginx requirement). For HTTPS, run `cloudflared` or `ngrok http 3100` against the slot-derived web port |

## 6. Operational guardrails

- **One profile per process group.** Never run `docker:local` and `docker:stage` against the same `COMPOSE_PROJECT_NAME`; the script defaults the project name to `ai-saas-<branch-slug>` to keep them apart.
- **Branch-locked slots.** `scripts/docker-local.sh` derives the slot from `git symbolic-ref --short HEAD`. Detached HEADs fall back to a content-hash slot so the stack still gets a stable block.
- **`docker:stage` is the only profile that allows a remote DB.** The local script refuses a Neon URL unless `ALLOW_REMOTE_DATABASE=true` is set explicitly. Stage refuses to run without `DATABASE_URL`.
- **No new HTTP services for the agent.** The agent runs inside `control_api`. Adding a separate `:8081` agent port would violate rule R11 (Local Lite process count) and rule R12 (MSA separation belongs in `docker:prod`).

## 7. Verification commands

```bash
# Local
pnpm docker:local
curl -fsS http://localhost:${FOUNDATION_PORT}/healthz
curl -fsS http://localhost:${WEB_PORT}/

# Stage
pnpm docker:stage
curl -fsS http://localhost:${FOUNDATION_PORT}/healthz
psql "${DATABASE_URL_UNPOOLED}" -c "select 1"

# Prod (validate compose in CI only — no host bind)
docker compose -f docker/prod/compose.yaml config -q

# Agent contract (worktree-independent)
uv run --locked python -m pytest -q tests/test_proposal_verified_change_agent.py tests/test_runtime_boundaries.py
```