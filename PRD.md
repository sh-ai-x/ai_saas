# PRD — Profile Subscription, Token Entitlements, and Billing Operations

## 1. Frame

- **Goal:** Ship an authenticated profile and admin subscription experience that shows the user's plan, subscription state, current and next billing dates, token limit and usage, supports cancellation at the current period end, and keeps Neon entitlements synchronized with Toss Payments lifecycle events.
- **Target user:** A paying solo AI SaaS developer who needs to understand access, remaining tokens, and what will happen at the next renewal without contacting support.
- **Situation:** The application has pricing, payment-order, subscription, billing-event, quota, and admin foundations, but users cannot see their own subscription lifecycle or token consumption and operators cannot reliably inspect every user's renewal/cancellation state.

## 2. Validate

### Independent evidence

1. **User requirement (2026-09-28):** The request explicitly asks for profile subscription/plan status, cancellation, token limit and usage, Toss state changes, Neon review, and per-user admin visibility, including cancellation at period end and automatic renewal.
2. **Repository evidence (2026-09-28):** `apps/web/db/schema/pricing.ts` already defines `pricing_plans`, `pricing_options`, `payment_orders`, `subscriptions`, `billing_events`, and `admin_audit_events`, while the web surface has pricing/admin pages but no user subscription profile flow.
3. **Neon evidence (2026-09-28):** Read-only inspection of project `ai_saas` production found the expected billing tables, 1 user, 0 subscriptions, 0 payment orders, 0 billing events, and 16 admin audit events; staging has 2 users, 0 subscriptions, 15 payment orders, 0 billing events, and 25 admin audit events. The current `subscriptions` table has `current_period_start/end` and `cancel_at_period_end`, but no explicit cancellation timestamp, termination timestamp, next billing timestamp, failed-payment state, or event ordering/version fields.
4. **Provider evidence (2026-09-28):** The existing `TossPaymentsAdapter` exposes checkout/confirmation/webhook/reconcile capability, but `transition_subscription()` is a stub. Toss's official auto-billing guide states that the merchant must schedule calls to `POST /v1/billing/{billingKey}`; Toss does not provide the recurring schedule, and a cancellation is implemented by not calling the billing API on the next billing date. [Toss auto-billing API guide](https://docs.tosspayments.com/guides/v2/billing/integration-api)
5. **SOT/operations evidence (2026-09-28):** `.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md` requires provider-neutral normalized events, idempotent inbox processing, entitlement transitions, append-only audit, server-side admin authorization, and access preservation through a defined cancellation end time.

### Value score

Planning assumptions: 240 value units per retained paying user per year, 25 reachable early adopters, and 1,200 value/cost units for a bounded vertical slice covering schema, lifecycle, metering, UI, admin, and verification.

`value_score = (240 × 25) / 1,200 = 5.0` — **PASS** (threshold ≥ 3.0).

### Ambiguity loop

`ambiguity_score: 10 → 8 → 6 → 4 → 3` — **PASS**.

- The first narrowing fixed the target to an authenticated end-user profile plus a privileged admin read surface.
- The second fixed cancellation semantics: set `cancel_at_period_end`, preserve access until `current_period_end`, and prevent the next Toss charge.
- The third fixed billing ownership: Toss proves and charges; the application owns scheduling, normalized state, entitlement, usage period, and reconciliation.
- The fourth fixed metering semantics: actual input/output token usage is append-only and idempotent; current-period usage is compared to a plan snapshot, not recomputed from mutable plan text.
- The final narrowing fixed MVP boundaries: no refunds, proration, plan switching, payment-method self-service, or second provider implementation in this phase.

### Lifecycle decisions

| Internal state/event | User access | Data effect | UI meaning |
|---|---|---|---|
| `pending` / billing authorization started | No paid entitlement until first charge is confirmed | Store pending order and provider references; do not grant quota | Payment setup in progress |
| `active` / first charge or renewal succeeded | Yes | Set period start/end, `next_billing_at`, clear cancellation/failure, snapshot plan limits, reset the new period's usage bucket | Active plan; renewal date is visible |
| `cancel_scheduled` (`active` + `cancel_at_period_end=true`) | Yes through `current_period_end` | Persist requested/confirmed cancellation timestamps and a durable idempotency key; scheduler skips the next billing call | “Cancels on {period end}”; show Resume |
| cancel resumed before period end | Yes | Clear cancel flag/timestamps; scheduler may charge at next billing date | Active; automatic renewal restored |
| renewal attempt `past_due` / payment failed | Grace period policy: keep access for the configured short window, then degrade to free/read-only | Record attempt, provider error, retry count, next retry; never reset usage on a failed renewal | Payment failed; update payment method/support path |
| `expired` / `canceled` at period end | No paid entitlement after end time; free fallback remains available | Close subscription, end entitlement, retain immutable history and usage ledger | Plan ended; choose a new plan |
| provider event duplicate/out of order/unknown | No unsafe downgrade or grant | Inbox deduplicates by provider/event id and idempotency key; stale events are recorded and reconciled, not applied blindly | “Sync pending” only for operators, not a false success |

Toss implementation detail: the scheduler, not Toss, owns the `next_billing_at` job. A period-end cancellation must therefore mark the local subscription before the scheduler's idempotent charge boundary and skip the next `POST /v1/billing/{billingKey}` call; deleting the billing key is optional cleanup after access ends, not the source of truth. A successful renewal advances the period and resets the plan-period usage bucket. A failed renewal does not reset it.

### Neon review and migration direction

The existing Neon schema is a useful catalog/order/subscription starting point, but it is not sufficient for subscription operations or token reporting. The build must add reviewed Drizzle migrations rather than mutate production directly:

- Extend `subscriptions` with explicit internal/provider status, `cancel_requested_at`, `canceled_at`, `ended_at`, `next_billing_at`, `grace_until`, `last_payment_at`, `last_payment_error`, `version`, and a non-secret billing-token reference. Keep raw billing keys out of client responses and logs; use a secret reference/encrypted server-side store according to the deployment secret policy.
- Add provider event ordering and processing fields to `billing_events` (received/verified/applied/ignored, occurred-at, processed-at, failure reason, aggregate/subscription reference, payload version) and enforce provider + external event uniqueness.
- Add a subscription transition/history table for immutable state changes and reconciliation evidence. Every user cancellation, resume, renewal, failure, expiry, and admin repair must have an audit/transition record.
- Extend plan quota data with explicit token dimensions (`monthly_input_tokens`, `monthly_output_tokens`, or one documented total-token policy) and a stable plan-version/snapshot identifier. Add a token usage period table plus append-only token usage entries with user, subscription/period, run/request, input/output/total tokens, source, and idempotency key.
- Add the indexes needed by profile reads (`user_id + status`, `next_billing_at`, `current_period_end`), scheduler claims, admin filters (`status`, `provider`, `next_billing_at`), and usage aggregation (`user_id + period + created_at`). Enforce one active/pending paid subscription per user/tenant through an application transaction and a suitable partial unique index.
- Use Neon `staging` for migration verification and `production` only through the existing preflight/plan/apply/verify release process. The current production data is nearly empty, but the migration must be safe for future rows and preserve existing mock/one-time catalog records.

## 3. Non-goals

1. **Immediate cancellation, refunds, or retroactive token removal.** Rationale: the requested business rule is cancel-at-period-end and access remains valid through the paid period. Breach response: create a separate refund/early-termination policy and provider contract; do not change this state machine.
2. **Plan switching, proration, credits, or payment-method self-service.** Rationale: each introduces financial and entitlement edge cases beyond the first profile lifecycle slice. Breach response: open a separate plan-change design with explicit proration and effective-date rules.
3. **A second payment provider or provider-specific UI contracts.** Rationale: the domain must remain provider-neutral while Toss is the requested provider. Breach response: extend the normalized capability port and add a separate provider phase.
4. **Replacing the existing admin authorization/audit boundary or exposing raw billing credentials.** Rationale: this feature consumes the existing server-side admin guard and append-only audit model. Breach response: security review first; never add direct browser-to-Neon writes or return billing keys.
5. **Usage-based overage billing or unlimited-token plans.** Rationale: MVP reports and enforces a fixed plan-period token allowance. Breach response: define a separate metered-pricing ledger and invoice/retry policy.

## 4. Phase plan

Phase index: `phases/profile-subscription/index.json`

### Step 0 — neon-billing-model

Add the Neon/Drizzle schema and migration for subscription lifecycle timestamps/status history, provider event processing, plan token limits, subscription-period snapshots, and append-only token usage. Define the provider-neutral internal state machine and transactional invariants before any UI or provider integration.

### Step 1 — toss-subscription-lifecycle

Complete the Toss recurring-payment port and adapter contract: billing-auth success, billing-key issuance, first charge, scheduled renewal, cancel-at-period-end, resume, failed charge/grace retry, expiry, webhook verification, idempotency, out-of-order handling, and reconciliation. Add a durable scheduler claim path because Toss does not schedule recurring calls.

### Step 2 — token-metering-entitlements

Connect run completion/actual model usage to an atomic token reservation/commit/release ledger. Resolve the active plan-period snapshot, expose current/limit/remaining input/output/total token values, enforce limits before dispatch, and ensure renewal/cancellation/failure semantics match Step 1 without double-granting or double-counting.

### Step 3 — profile-subscription-ui

Add authenticated profile subscription APIs and page. Show plan name/status, paid-through date, next automatic billing date, cancellation scheduled date, renewal/failure notice, token limits and usage progress, and safe actions to cancel at period end or resume. Ensure the page reads server-owned state and never trusts redirect/query parameters for entitlement.

### Step 4 — admin-operations-verification

Add the admin per-user subscription/usage view with search and filters, event/transition/reconciliation details, and audited repair/resume/cancel controls where explicitly allowed. Complete migration rollout checks, scheduler/reconciliation observability, focused contract/e2e tests, failure/duplicate/out-of-order fixtures, and operator documentation.

## 5. Acceptance criteria

1. **Schema and invariants:** Neon/Drizzle migrations add the subscription lifecycle, event processing, token-limit, period-snapshot, and usage-ledger fields/tables; a contract test proves one active subscription per user/tenant, immutable transition history, safe migration of current rows, and profile/admin query indexes.
2. **Toss lifecycle:** Contract tests cover billing-auth → billing-key → first charge, successful renewal, cancel-at-period-end (no immediate access loss and no next scheduled charge), resume, failed renewal/grace, expiry, duplicate/out-of-order/unknown events, and reconciliation; every provider effect is server-side and idempotent.
3. **Token entitlement:** A usage test proves input/output/total token accounting, reservation/commit/release, plan-period limits, quota blocking before dispatch, reset only after successful renewal, retention through a scheduled cancellation period, and no duplicate usage on retries.
4. **Profile experience:** An authenticated user can read a single server-owned subscription summary and token usage projection and can schedule or resume cancellation; the UI shows plan status, paid-through date, next billing date, scheduled cancellation date, and clear failed-payment/expired states without exposing secrets.
5. **Admin and operations:** An authorized admin can search users and see per-user plan/status, period dates, cancellation/renewal/failure state, and token usage; mutations require reason/idempotency and append before/after audit records; staging migration verification, scheduler reconciliation, and focused web/Python/e2e suites pass.

## 6. Hand-off

- **Phase index:** `phases/profile-subscription/index.json`
- **Build order:** Step 0 → Step 1 → Step 2 → Step 3 → Step 4; each step owns its schema/API/UI/test slice and consumes only completed upstream contracts.
- **Operational boundary:** Use Neon staging for migration rehearsal; do not write production data during implementation. Keep Toss secrets server-only and use test keys for sandbox verification.
- **Review artifact:** `/dev-kit:proposal reviewing/profile-subscription` if the proposal renderer is enabled in the next planning hand-off.
- **Next invocation:** `/dev-kit:build`
