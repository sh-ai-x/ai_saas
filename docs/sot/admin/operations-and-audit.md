---
doc_id: admin-operations-audit
domain: admin
purpose: Define safe support operations, privileged authorization, and auditability.
read_when:
  - changing super-admin pages or admin APIs
  - changing a user's plan, credits, account status, or support state
  - investigating a billing or entitlement discrepancy
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../auth/google-oauth.md
  - ../billing/subscriptions-and-entitlements.md
  - ../billing/payment-webhooks-and-ledger.md
  - ../security/safety-boundaries.md
source_of_truth: contract
owner: operations-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Admin Operations and Audit

## Baseline from `mysaas`

`../mysaas/my-saas/src/lib/auth/withSuperAdminAuthRequired.ts:14-50` provides
a common super-admin authorization wrapper. Admin APIs cover searchable and
paginated users (`src/app/api/super-admin/users/route.ts:7-63`), plan mutation
(`src/app/api/super-admin/users/[id]/plan/route.ts:10-35`), credit history and
adjustment (`src/app/api/super-admin/users/[id]/credits/route.ts:21-121`), and
plan statistics (`src/app/api/super-admin/stats/plans/route.ts:8-25`). Credit
adjustments record an admin ID, email, and reason.

## MVP operating model

Start with a super-admin role if that matches product scope, but keep the
authorization boundary replaceable by RBAC. Do not treat an email allowlist as
the long-term security model. Before production, assess MFA/step-up auth,
least privilege, separation of duties, and break-glass access.

## Privileged-action contract

Every mutation must:

1. Resolve an authenticated operator.
2. Verify role and resource scope.
3. Validate the request schema and target state.
4. Read the current state and capture a safe before snapshot.
5. Require a reason; require confirmation for high-impact actions.
6. Apply the shared domain use case, not a direct table mutation.
7. Record actor, action, target, reason, before, after, source, correlation ID,
   and timestamp in an append-only audit event.
8. Return a safe result without secrets or unnecessary PII.

## Supported operations

- Search and inspect a user with pagination and redaction.
- View current plan, provider identifiers, entitlement status, credit balance,
  and relevant event history.
- Change a plan through the entitlement transition contract.
- Add or deduct credits only through a typed credit ledger adjustment.
- Ban, unban, or delete a user only through a high-impact confirmation path.
- Inspect failed webhooks and initiate a safe replay or reconciliation.
- View plan-distribution and operational health statistics.

## Guardrails

- No admin UI action bypasses the server-side authorization wrapper.
- No plan or credit adjustment silently changes provider state.
- No destructive action is irreversible without an approved recovery path.
- Admin list endpoints are paginated, rate-limited, and redact sensitive fields.
- Audit events are not editable by normal admins.
- Support agents should see the minimum PII needed for the task.

## Verification evidence

- Unauthenticated and non-admin calls return denial responses.
- Admin mutation tests require a reason and record actor/before/after.
- Concurrent plan/credit operations produce deterministic results.
- Audit events can reconstruct who changed what and why.
- Reconciliation views identify divergence between provider, ledger, and user
  entitlement state.

## Sources

- [Anthropic: Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents)
- Baseline: `../mysaas/my-saas/src/lib/auth/withSuperAdminAuthRequired.ts:14-50`,
  `src/app/api/super-admin/users/route.ts:7-63`,
  `src/app/api/super-admin/users/[id]/credits/route.ts:69-121`,
  `src/app/api/super-admin/stats/plans/route.ts:8-25`.
