---
id: operations
category: OPERATE
title: Operations and recovery
summary: Rotate credentials, investigate webhooks, and roll back safely.
---
# Operations and recovery

## Credential rotation

Add the replacement secret to the runtime secret store, deploy, run the
provider smoke check, then revoke the old secret. Never write credentials to
`.env`, Git, logs, or issue comments.

## Webhook recovery

Inspect the provider inbox and normalized status. Replaying the same signed
event is safe because provider and idempotency keys are unique. Amount
mismatches, unknown orders, and invalid signatures fail closed.

## Provider rollback

Stop new checkout creation, reconcile pending orders, then switch provider in a
reviewed environment change. Production never silently falls back to mock.

## Cost pause

Quota exhaustion pauses a run before model dispatch or credit reservation.
Increase the reviewed budget explicitly; do not silently upgrade infrastructure.
