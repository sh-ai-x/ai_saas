---
doc_id: billing-admin-runbook
domain: billing
purpose: Provide short operator checklists that link to the authoritative billing and admin contracts.
read_when:
  - performing support operations
  - responding to a payment, subscription, or credit incident
audience:
  - operator
  - user
  - agent
prerequisites:
  - billing/subscriptions-and-entitlements.md
  - billing/payment-webhooks-and-ledger.md
  - admin/operations-and-audit.md
source_of_truth: contract
owner: operations-platform
last_reviewed: 2026-09-17
change_impact: medium
---

# Billing and Admin Runbook

This is a short navigation runbook. The detailed contracts live in
[subscriptions and entitlements](billing/subscriptions-and-entitlements.md),
[payment webhooks and ledger](billing/payment-webhooks-and-ledger.md), and
[admin operations and audit](admin/operations-and-audit.md).

## Scope and contract

This runbook covers first-response navigation for billing and account
operations. It does not authorize direct database edits or override the
linked billing, ledger, or admin contracts.

## User paid but has no access

1. Open the user from the admin search.
2. Locate provider order/payment/subscription ID.
3. Locate the provider event ID and processing state.
4. Check signature verification and deduplication result.
5. Compare provider state, local event, entitlement, and credit ledger.
6. Replay only through the verified event path; never grant access by editing
   the displayed balance without an audited ledger effect.

## Duplicate credit or entitlement report

1. Search by provider event/payment ID and internal idempotency key.
2. Confirm whether the ledger has one or multiple effects.
3. Freeze further manual changes if the event is still processing.
4. Use the reconciliation procedure and record the operator reason.

## Admin plan or credit adjustment

1. Confirm the operator role and target user.
2. Read the relevant contract before acting.
3. State the reason and expected before/after values.
4. Apply the shared use case.
5. Confirm the audit event and communicate the resulting entitlement.

## Verification evidence

- The operator can locate the provider event, internal idempotency key, and
  resulting entitlement or ledger effect.
- Replayed events produce no duplicate grant or debit.
- Every manual adjustment has an authenticated actor, reason, and audit event.

## Related documents

- [Subscriptions and entitlements](billing/subscriptions-and-entitlements.md)
- [Payment webhooks and ledger](billing/payment-webhooks-and-ledger.md)
- [Admin operations and audit](admin/operations-and-audit.md)
- [Verification, release, and incident response](verification/release-and-incident.md)

## Sources

This runbook delegates normative behavior to the linked contracts and their
official provider sources; it is not an independent provider specification.
