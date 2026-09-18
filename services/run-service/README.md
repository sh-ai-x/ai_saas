# run-service

Owns the durable run lifecycle, request idempotency, replay sequence, and
run-event projection. `SQLiteRunStore` persists run state, checkpoints, and
events; `RunService` reserves credits before dispatching a `run.requested`
envelope to an injected Inngest-compatible dispatcher.

The public stream is `RunService.sse(run_id, tenant_id, last_event_id=...)`.
It reads persisted events on every call, so reconnects do not depend on a live
worker process. Input envelopes remain in the run store for worker recovery,
but are never copied into workflow events or SSE payloads.

Supported lifecycle states are `queued`, `running`, `waiting_approval`,
`quota_paused`, `completed`, `failed`, and `cancelled`. Approval, quota pause,
and cancellation are server-side transitions; tenant scope is checked before
status, approval, cancellation, or replay access.
