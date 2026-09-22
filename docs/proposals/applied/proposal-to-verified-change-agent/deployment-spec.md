# Deployment Spec — Proposal-to-Verified-Change Agent + Foundation

> Companion to [`implementation-status.md`](./implementation-status.md). Defines the runtime profiles, host port strategy, and the scripts that drive them.
>
> This is the Local Lite + offline slice; the proposal rules R1–R14 ([`rules/proposal-to-verified-change-agent.md`](../../../rules/proposal-to-verified-change-agent.md)) still apply.

## 1. TL;DR

- **local dev** → `pnpm docker:local` (hot reload, local Postgres, fake provider, sandbox = deterministic)
- **stage** → `pnpm docker:stage` (prod-shape images, Neon DB, slot-derived ports `3200/8280/56433`)
- **prod** → **Vercel** for the web, foundation API deployed alongside, Neon for Postgres. **No `docker:prod`.** The `docker/prod/compose.yaml` file is kept only for `docker compose config` validation in CI.
- **Stripe is not implemented.** Payments ship with Toss (KR primary) and LemonSqueezy (global fallback); both adapters are wired, neither is on by default in stage.

## 2. Payment providers — current state

| Provider | Status | Used for |
|---|---|---|
| **Toss Payments** (`TOSS_CLIENT_KEY` / `TOSS_SECRET_KEY` / `TOSS_WEBHOOK_SECRET`) | ✅ Wired (sandbox + recurring billing) | KR primary checkout + subscription sandbox (`PAYSUB` flow) |
| **LemonSqueezy** (`LEMONSQUEEZY_STORE_ID` / `LEMONSQUEEZY_VARIANT_ID` / `LEMONSQUEEZY_API_KEY`) | ✅ Env wired, adapter behind `PAYMENT_PROVIDER` flag | Global fallback |
| `MOCK_PAYMENTS_ENABLED=true` | ✅ Default in local + stage | Dev / CI |
| **Stripe** | 🚫 **Not implemented.** Do not add Stripe keys; there is no adapter for them. If a future ticket asks for Stripe, create a new project pack or ADR — do not enable it implicitly. |

`PAYMENT_PROVIDER` accepts `mock` (default), `toss` (sandbox or live), or `lemon_squeezy`. Anything else is rejected.

## 3. Topology per profile

### 3.1 `docker:local` — developer loop

The agent **adds no new HTTP services**. It is a Python library that runs inside the foundation API (`services/control_api`) and uses the same SQLite state. Adding a separate agent container in Local Lite would break rule R11 (≤ 2 long-lived processes) and rule R12 (nginx edge in production only).

```
   browser ──▶ nginx :8080 ──▶ foundation :8000 ──▶ SQLite (./data)
                          (control_api + workflow + sandbox inline)

   Long-lived processes: 2 (nginx, foundation)
   Provider mode: fake
   Sandbox mode: deterministic (allowlisted fixture commands)
```

### 3.2 `docker:stage` — staging with cloud DB

Production-shape images (Next.js `runner`, foundation `prod`) pointed at a Neon cloud DB. Exposes a separate slot range so it cannot collide with a developer's local stack.

```
   browser ──▶ nginx :8080 ──▶ foundation :8000 ──▶ Neon (DATABASE_URL)
                          │
                          └─▶ web :3000 (Next.js runner, BFF)

   Long-lived processes: nginx, foundation, web = 3
   Provider mode: fake (MOCK_PAYMENTS_ENABLED=true)
   Slot range: 3200 / 8280 / 56433 (+ 10·slot)
```

### 3.3 Prod — **Vercel** (not Docker)

```
                  ┌──────────────────────────────────────────────────┐
                  │ Vercel (managed edge)                              │
                  │                                                    │
   browser ──▶ Vercel CDN/Edge ──▶ Vercel Function (Next.js) :443    │
                                       │                              │
                  ┌────────────────────┼───────────────────────┐      │
                  │                    │                       │      │
                  ▼                    ▼                       ▼      │
              Vercel-hosted      Vercel Function            Vercel   │
              Next.js (web)      (foundation API) :8000     Cron/ISR │
                                       │                              │
                  ┌────────────────────┼───────────────────────┐      │
                  │                    │                       │      │
                  ▼                    ▼                       ▼      │
              Neon (pooled)     Foundation-bound work     │ Vercel KV │
                              (agent_orchestrator          │ (caches)  │
                              + delivery-gateway inline)               │
                  └───────────────────────────────────────────────────┘

   Long-lived processes: Vercel manages scale; foundation runs as a
   Vercel Function with the agent_orchestrator + delivery_gateway inline.
   No Docker. No nginx (Vercel handles TLS).
```

#### Vercel deployment — concrete shape

- **Web** → Vercel project `ai-saas-web` (Next.js App Router). `vercel.json` pins build command, output dir, and framework. Region pinned to `icn1` (Seoul) for KR latency.
- **Foundation API** → Vercel project `ai-saas-foundation` (Python Function). Built from `docker/prod/foundation.Dockerfile` via `vercel deploy --prebuilt`. Exposed at `https://foundation.<domain>` behind Vercel auth.
- **Database** → Neon prod branch (pooled URL → runtime, unpooled URL → migrations).
- **Cron / scheduled jobs** → Vercel Cron (e.g. webhook retries, ledger cleanup).
- **Secrets** → Vercel Environment Variables per environment (`production`, `preview`). Never baked into the image.
- **TLS** → Vercel-managed certificate. No nginx. No cert files in repo.

#### Vercel env vars (production)

```env
APP_ENV=production
DEPLOYMENT_PROFILE=vercel-prod
APP_BASE_URL=https://<prod-domain>
FOUNDATION_PUBLIC_URL=https://foundation.<prod-domain>
DATABASE_URL=<neon-pooled>
DATABASE_URL_UNPOOLED=<neon-direct>
APP_SECRET_KEY=<32-byte hex, generated>
BETTER_AUTH_SECRET=<32-byte hex, generated>
CONTRACT_VERSION=v1
PAYMENT_PROVIDER=toss
MOCK_PAYMENTS_ENABLED=false
PAYMENT_SANDBOX=false
TOSS_CLIENT_KEY=<live>
TOSS_SECRET_KEY=<live>
TOSS_WEBHOOK_SECRET=<live>
FAQ_OPENAI_ENABLED=false          # turn on only after the staging gate
OPENAI_API_KEY=<server-only>      # if FAQ_OPENAI_ENABLED=true
NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
GOOGLE_CLIENT_ID=<live>
GOOGLE_CLIENT_SECRET=<live>
OTEL_ENABLED=true
OTEL_SAMPLE_RATE=0.1
OTEL_EXPORTER=otlp                # or "memory" for ephemeral preview
RUN_QUOTA_MAX_RUNS=10
RUN_QUOTA_MAX_UNITS=100
RUN_QUOTA_PERIOD_SECONDS=86400
```

## 4. Host port strategy (local + stage)

### 4.1 Why slot-based allocation, not fixed ports

Multiple worktrees run in parallel during development. Fixed ports collide with Next.js dev, Stripe CLI, ngrok, and the previous worktree's container. The slot script derives a stable **slot** per branch and assigns a contiguous block of three host ports (web + foundation + postgres). Each port is collision-checked against `lsof` before being claimed.

### 4.2 Slot table

| Profile | Web | Foundation | Postgres | Slot math |
|---|---:|---:|---:|---|
| `docker:local` (slot `S`) | `3100 + 10·S` | `8180 + 10·S` | `55433 + 10·S` | hash(branch) → slot 0–39 |
| `docker:stage` (slot `S`) | `3200 + 10·S` | `8280 + 10·S` | `56433 + 10·S` | hash(branch) → slot 0–39 |
| Vercel prod | n/a (managed) | n/a (managed) | n/a (Neon) | — |

Slot math guarantees **non-overlapping ranges** because the prefixes differ (`31xx` vs `32xx`, `81xx` vs `82xx`, `554xx` vs `564xx`). Two worktrees on the same profile still avoid each other because the slot is per-branch.

### 4.3 Why NOT 3000 / 3019

`3000` collides with:

- Next.js dev server when the container is down
- ngrok / VS Code Code-Server / Jupyter
- The previous worktree's container if `docker:local:down` was skipped

`3019` is worse — it does not match any known range (`31xx`, `32xx`, `554xx`, `564xx`). The slot table keeps every host port inside a discoverable window. Anything outside is a typo or a forgotten manual override.

**Recommendation:** stop binding host ports `3000` and `3019` directly. Use the slot table:

```bash
pnpm docker:local          # slot 0 → web :3100, foundation :8180, postgres :55433
pnpm docker:local:status   # see assigned ports
```

If you must bind to `3000` for a public demo, use Vercel — it terminates TLS at the edge and the web container stays on the private network.

### 4.4 nginx in Local Lite — port 8080, not 80

`infra/nginx/local-lite.conf` listens on **`8080`**, not `80`, because binding `80` requires root and conflicts with macOS AirPlay on port 5000/7000. Vercel owns `443` (TLS) and `80` (HTTP→HTTPS redirect) in production.

## 5. Profile decision matrix

| Need | Profile |
|---|---|
| Edit Next.js code with hot reload | `docker:local` |
| Test foundation API + workflow + fake provider | `docker:local` |
| Reproduce cloud-only Postgres behavior | `docker:stage` |
| Verify migration + Drizzle against Neon | `docker:stage` |
| Stage demo for a stakeholder | `docker:stage` |
| Production deployment | **Vercel** (`vercel deploy`) |
| CI / lint that only needs to validate compose | `docker compose -f docker/prod/compose.yaml config` |
| Stripe checkout | 🚫 Not supported. Use Toss or LemonSqueezy. |

## 6. Operational guardrails

- **One profile per process group.** Never run `docker:local` and `docker:stage` against the same `COMPOSE_PROJECT_NAME`; the script defaults the project name to `ai-saas-<branch-slug>` so they stay apart.
- **Branch-locked slots.** The slot script derives the slot from `git symbolic-ref --short HEAD`. Detached HEADs fall back to a content-hash slot so the stack still gets a stable block.
- **`docker:stage` is the only profile that allows a remote DB.** The local script refuses a Neon URL unless `ALLOW_REMOTE_DATABASE=true` is set explicitly. Stage refuses to run without `DATABASE_URL`.
- **No new HTTP services for the agent.** The agent runs inside `control_api`. Adding a separate `:8081` agent port would violate rule R11 (Local Lite process count) and rule R12 (MSA separation belongs in Vercel, not in the Docker profiles).
- **No Stripe.** Toss and LemonSqueezy only. Stripe is explicitly out of scope for this proposal.

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

# Prod (Vercel)
vercel deploy --prod
curl -fsS https://<prod-domain>/healthz
vercel env ls --environment production

# CI: validate the legacy prod compose shape
docker compose -f docker/prod/compose.yaml config -q

# Agent contract (worktree-independent)
uv run --locked python -m pytest -q \
  tests/test_proposal_verified_change_agent.py \
  tests/test_runtime_boundaries.py
```