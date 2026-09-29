# step2.md

## Status

completed

## Read first

- `PRD.md` §2 lifecycle decisions and Neon review
- `services/metering_billing/quota.py`
- `services/agent_worker/runtime.py`
- `services/run_service/service.py`
- `services/agent_worker/providers.py`
- `tests/test_step4_low_cost.py`
- `packages/contracts/sse/v1/run-event.json`

## Task

Connect actual model usage to a durable token metering/entitlement service. Define the plan-period limit snapshot and token dimensions, reserve before dispatch, commit actual input/output/total usage on completion, release unused reservations on pre-dispatch failure, and enforce limits before work starts. Add idempotent run/request usage keys and a profile projection with limit, used, remaining, percentage, period start/end, and source freshness. Successful renewal must create a new period and reset the period counters; scheduled cancellation must preserve the current period; failed renewal/grace must not reset usage; expiry must fall back to the free policy without deleting history.

## Acceptance Criteria

1. Usage tests prove input/output/total token accounting, atomic reservation/commit/release, quota blocking before dispatch, successful-renewal reset, cancellation-period retention, failed-renewal retention, and retry idempotency.
2. A single server-owned projection returns current and limit values for the profile and admin surfaces without aggregating mutable plan JSON at read time.
3. Concurrency tests show no negative remaining balance, double charge, or double usage entry when a run, renewal, webhook, or scheduler operation is retried.

## Verification & Status Update

```bash
uv run --locked python -m unittest tests/test_step4_low_cost.py tests/test_run_worker_streaming.py tests/test_billing.py
pnpm --dir apps/web test -- --runInBand usage quota entitlement
pnpm --dir apps/web typecheck
```

## Don't

- Do not treat request count as token usage when provider usage is available.
- Do not reset a canceled user's current-period quota before `current_period_end`.
- Do not implement overage billing, unlimited plans, or a mutable aggregate with no ledger source.
