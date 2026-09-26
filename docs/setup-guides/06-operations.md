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

## Foundation service deploy (Fly.io)

The Python foundation service (`foundation/`) is hosted on Fly.io and
proxied from Vercel via `FOUNDATION_API_URL`. The first-time setup and
each routine deploy follow different paths.

**One-time setup** (operator shell, after `fly auth login`):

```bash
fly apps create ai-saas-foundation --org personal
fly volumes create foundation_state --size 1 --region nrt --app ai-saas-foundation --yes
fly secrets set \
  DATABASE_URL='<neon pooled url>' \
  APP_SECRET_KEY='<openssl rand -base64 32>' \
  APP_BASE_URL='https://ai-saas-foundation.fly.dev' \
  APP_ENV='staging' \
  AUTH_PROVIDER='local-mock' \
  MOCK_PAYMENTS_ENABLED='true' \
  CONTRACT_VERSION='v1' \
  WORKFLOW_PROVIDER='local' \
  AGENT_PROVIDER_MODE='fake' \
  PAID_INFRASTRUCTURE='false' \
  AWS_WORKER_ENABLED='false' \
  OTEL_ENABLED='true' \
  PAYMENT_PROVIDER='mock' \
  --app ai-saas-foundation
```

Set `FLY_API_TOKEN` as a GitHub Actions secret (Settings → Secrets →
Actions) so `.github/workflows/foundation-fly-deploy.yml` can deploy.

**Subsequent deploys** are automatic: pushes to `main` that touch
`foundation/`, `docker/prod/foundation.Dockerfile`, `fly.toml`, or the
workflow file trigger `.github/workflows/foundation-fly-deploy.yml`.
The workflow builds remotely via `flyctl deploy --remote-only`, runs
`foundation.contract_check` as the release command, and smoke-tests
`https://ai-saas-foundation.fly.dev/healthz` for up to 50s before
failing.

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
