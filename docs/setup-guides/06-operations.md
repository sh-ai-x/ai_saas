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
