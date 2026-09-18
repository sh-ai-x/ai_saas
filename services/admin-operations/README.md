# admin-operations

Owns privileged use cases and append-only audit records. The Python
implementation is in `services/admin_operations/`; mutations require
server-side authorization, target scope, reason, and idempotency.

Plan changes use an entitlement port and credit changes use a ledger port;
the UI never mutates provider or billing state directly. Every successful
mutation has actor, target, reason, correlation, and before/after evidence.
