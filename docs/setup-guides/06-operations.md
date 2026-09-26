# Operations and recovery

Rotate credentials through the runtime secret store, verify provider health,
then revoke the old value. Never write secrets to `.env`, Git, CI output, or
telemetry.

Inspect the provider inbox and normalized status when recovering webhooks.
Replaying the same signed event is safe because provider and idempotency keys
are unique; amount mismatches and invalid signatures fail closed.

Stop new checkout creation and reconcile pending orders before switching a
provider. Production never silently falls back to mock. Quota exhaustion pauses
runs before provider dispatch or credit reservation.

## Foundation service deploy (Fly.io) — staging smoke-test

The Python foundation service (`foundation/`) is hosted on Fly.io and
proxied from Vercel via `FOUNDATION_API_URL`. The current
`ai-saas-foundation` app is a **staging smoke-test** instance: it boots
with `APP_ENV=staging`, `AUTH_PROVIDER=local-mock`, and a fake agent
provider so the Next.js `/app` route can be exercised end-to-end
without a real payment or AI provider integration. Production rollout
needs a separate guide (real Toss / LemonSqueezy credentials, real
OpenAI key, separate Fly app + secrets).

**One-time setup** (operator shell, after `fly auth login`):

```bash
fly apps create ai-saas-foundation --org personal
fly volumes create foundation_state --size 1 --region nrt --app ai-saas-foundation --yes
fly secrets set \
  DATABASE_URL='<neon pooled url>' \
  APP_SECRET_KEY='<openssl rand -base64 32>' \
  APP_ENV='staging' \
  AUTH_PROVIDER='local-mock' \
  MOCK_PAYMENTS_ENABLED='true' \
  AGENT_PROVIDER_MODE='fake' \
  PAYMENT_PROVIDER='mock' \
  PAID_INFRASTRUCTURE='false' \
  AWS_WORKER_ENABLED='false' \
  CONTRACT_VERSION='v1' \
  WORKFLOW_PROVIDER='local' \
  OTEL_ENABLED='true' \
  OTEL_SAMPLE_RATE='0.1' \
  RUN_QUOTA_MAX_RUNS='10' \
  RUN_QUOTA_MAX_UNITS='100' \
  RUN_QUOTA_PERIOD_SECONDS='86400' \
  --app ai-saas-foundation
```

Note: `APP_BASE_URL` is owned by `fly.toml [env]` (not `fly secrets`)
until a custom domain is added. Single source of truth.

Set `FLY_API_TOKEN` as a GitHub Actions secret (Settings → Secrets →
Actions) so `.github/workflows/foundation-fly-deploy.yml` can deploy.

**Trigger paths** (push to `main` re-deploys via the workflow when any
of these change; each one is `COPY`'d by `docker/prod/foundation.Dockerfile`):

| path | why it matters |
|---|---|
| `foundation/**` | the Python service source |
| `agent_platform/**` | `COPY agent_platform ./agent_platform` |
| `lib/**` | `COPY lib ./lib` |
| `project_packs/**` | `COPY project_packs ./project_packs` |
| `services/**` | `COPY services ./services` |
| `evaluators/**` | `COPY evaluators ./evaluators` |
| `packages/contracts/**` | `COPY packages/contracts ./packages/contracts` |
| `config/**` | `COPY config ./config` |
| `infra/**` | `COPY infra ./infra` |
| `docker/prod/foundation.Dockerfile` | the build recipe itself |
| `pyproject.toml` / `uv.lock` | dependency graph (affects `uv sync --frozen`) |
| `fly.toml` | platform config (region, ports, mounts, checks) |
| `.github/workflows/foundation-fly-deploy.yml` | the deploy recipe itself |

**Subsequent deploys** are automatic: pushes to `main` that touch any
of the paths above trigger `.github/workflows/foundation-fly-deploy.yml`.
The workflow builds remotely via `flyctl deploy --remote-only`;
`foundation.contract_check` runs once at build time inside the
Dockerfile (no `release_command`). The smoke-test loop polls
`https://ai-saas-foundation.fly.dev/healthz` for up to 100s (10
attempts × `(5s curl + 5s sleep)`) before failing.

**Smoke-test manually:**

```bash
curl -fsS https://ai-saas-foundation.fly.dev/healthz
# {"contract_version":"v1","deployment_profile":"free-portfolio","status":"ok"}
```

**Roll back** a bad release with `fly releases rollback --app ai-saas-foundation`
(the machine is replaced, persistent volume at `/var/lib/ai-saas` is
untouched). For a hard rollback, pick a prior machine image from
`fly releases --app ai-saas-foundation` and run
`fly deploy --app ai-saas-foundation --image <registry-image>`.
