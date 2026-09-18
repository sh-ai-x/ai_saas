# metering-billing

Owns provider capability ports, normalized events, pending orders, entitlement,
and the append-only ledger. Provider adapters live in the Python
`services.billing` package; domain code does not import provider SDKs.

`SQLiteCreditLedger` adds durable run reservations, idempotent usage commits,
and releases. Reservation tables are namespaced so the logical run metering
boundary can share the existing `credit_accounts` balance table without
coupling to the payment ledger schema.

`SQLiteQuotaCounter` is the profile admission gate. It atomically counts runs
and requested units per tenant/window; a limit produces a durable
`quota_paused` run before any credit reservation, so the free profile cannot
silently fall through to paid work.
