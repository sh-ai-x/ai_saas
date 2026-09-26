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

## Production migration history repair

The `migration-repair-prod.yml` workflow restores the canonical
`__drizzle_migrations` history on the production database after a
broken deploy. The job is gated by:

- the `production` GitHub Environment (manual approval required), and
- a `workflow_dispatch` input that must literally be `production`
  (typed, not selected from a dropdown).

Before dispatching, set every confirmation env var to the matching
literal:

```
CONFIRM_PRODUCTION_DB=production CONFIRM_HISTORY_REPAIR=production \
  pnpm --filter web migrate:repair --target production
```

The script refuses to run otherwise: APP_ENV must be `production`,
NEON_BRANCH must be `production`, and (for apply) the run must come
from GitHub Actions. The repair is idempotent — re-running on a
canonical history is a no-op that prints `already current; no repair
needed`.
