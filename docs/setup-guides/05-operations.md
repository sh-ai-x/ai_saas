# Operations and recovery

## Rotate credentials

Add the replacement credential to the runtime secret store, deploy, run the
provider health/sandbox smoke, and revoke the old credential. Never write it to
`.env`, Git, CI output, issue comments, or telemetry.

## Recover webhooks

Inspect the provider inbox and normalized status. Replaying the same signed
event is safe: provider event identity and idempotency keys are unique. Amount
mismatches, unknown orders, invalid signatures, and unknown states fail closed.

## Roll back

Stop new checkout creation, reconcile pending orders with the provider, and
preserve the existing provider selection until pending effects are settled.
Switching to mock is allowed only in local/test; production never silently
falls back to mock.

## Pause on cost

Quota exhaustion creates a durable paused run before model dispatch or credit
reservation. Increase the reviewed budget explicitly; do not upgrade Vercel,
Cloudflare, AWS, or provider plans automatically.
