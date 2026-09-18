Status: pending
Name: billing-adapters-ledger

Read first:
- `PRD.md`
- `docs/sot/billing/provider-adapter-architecture.md`
- `docs/sot/billing/payment-webhooks-and-ledger.md`
- `docs/sot/billing/providers/toss-payments.md`
- `docs/sot/billing/providers/lemon-squeezy.md`
- `docs/sot/billing/subscriptions-and-entitlements.md`
- `phases/ai-saas-foundation/step1.md`

Task:
Implement provider-neutral billing through Ports-and-Adapters. Define capability ports and a registry, then add Toss, Lemon Squeezy, and non-production mock adapters. Persist pending orders and provider inbox records, verify raw events, deduplicate by provider identity/idempotency key, normalize status, and apply entitlement/credit effects transactionally with concurrency-safe ledger rules. Enable one live provider per environment.

Acceptance:
- REQ-3: Real adapters and mock scenarios share the same inbox, normalized-event, entitlement, ledger, and audit path.

Verification:
python3 -m lib.intent_integrity --pre ai-saas-foundation

Don't:
- Do not grant access from a client success redirect.
- Do not let domain code import Toss or Lemon Squeezy SDKs.
- Do not use read-then-write balance mutation without an idempotency/concurrency guard.
