# PRD — Toss Payments Subscription Sandbox Integration

## 1. Frame

- Goal: Connect the existing subscription catalog and admin Toss enable switch to a verified Toss Payments V2 sandbox flow that can be exercised at localhost:3000 without charging a real payment method.
- Target user: A SaaS product administrator and developer validating a subscription checkout locally before production payment contracting.
- Situation: The catalog has subscription options and a Toss adapter, but the browser uses the normal one-time payment flow, admin provider selection can be shadowed by the mock environment default, and the server has no complete billing-auth-to-recurring-approval path.

## 2. Validate

### Independent evidence

1. **Toss Payments official V2 billing guide** — subscription services must issue a billing key after the first authentication and call the automatic billing approval API on each billing period; the browser flow uses `requestBillingAuth()` and the server receives `authKey` and `customerKey`. Source: [Toss Payments billing guide](https://docs.tosspayments.com/guides/v2/billing), [billing window integration](https://docs.tosspayments.com/guides/v2/billing/integration). Date: 2026-09-20.
2. **Repository implementation evidence** — `apps/web/components/pricing-catalog.tsx:16-29` currently submits one generic checkout and opens only `checkoutUrl`; `apps/web/app/payments/toss/success/route.ts:5-28` confirms only a normal `paymentKey`; `apps/web/lib/pricing/repository.ts:278-283` lets `PAYMENT_PROVIDER` override the persisted admin provider setting. Date: 2026-09-20.
3. **User/runtime signal** — the requested behavior is specifically that enabling Toss from the admin payment screen makes subscription test payment work locally, after a previous Foundation startup failure caused by an invalid `APP_SECRET_KEY`. This requires a reproducible sandbox setup and an end-to-end contract instead of a UI-only toggle. Date: 2026-09-20.

### Value score

Assumption for this implementation decision: $120 expected first-year value per validated SaaS user, 50 reachable early users, and $1,200 engineering/runtime cost.

`value_score = ($120 × 50) / $1,200 = 5.0` — PASS (threshold ≥ 3.0).

### Ambiguity loop

`ambiguity_score: 10 → 8 → 6 → 4 → 3` — PASS (threshold ≤ 3).

- 10: provider and subscription behavior were not yet mapped to code.
- 8: MCP guidance fixed the provider contract to Toss V2 billing auth and recurring approval.
- 6: repository tracing identified the env-provider override, generic browser payment call, and missing billing-auth route.
- 4: the web payment order/subscription tables were selected as the settlement authority for the catalog flow; the existing Foundation console payment path remains backward-compatible.
- 3: the phase is limited to first sandbox charge, idempotent settlement, and a documented local path; production scheduling and live operations remain out of scope.

## 3. Non-goals

1. **Live charging or production capture.** Rationale: the user explicitly requested sandbox-only validation. Breach response: reject the scope change and create a separate production-readiness plan with contract, key, webhook, and security review.
2. **Full production subscription operations.** Rationale: recurring schedules, retries, dunning, cancellation policy, refunds, and webhook tunnel operations are not required to validate the first sandbox charge. Breach response: record the request as a separate lifecycle/operations phase after this sandbox contract is green.
3. **Replacing the Foundation billing adapter or adding another provider.** Rationale: the web pricing order/subscription tables are the source of truth for this catalog flow, while the existing Foundation Toss path remains backward-compatible for the workspace console. Breach response: defer provider abstraction changes and preserve the current Toss-only change set.
4. **Authentication, pricing visual redesign, or unrelated admin authorization changes.** Rationale: only the payment selection and checkout contracts are in scope. Breach response: create a separate plan with its own tests and worktree.

## 4. Phase plan

Phase index: `phases/toss-subscription-sandbox/index.json`

### Step 0 — toss-subscription-sandbox-e2e

A red-first, end-to-end implementation covering the Toss V2 billing-auth browser handoff, server billing-key exchange and first recurring sandbox approval, idempotent entitlement/credit settlement, admin provider activation, container configuration, and setup-guide instructions.

## 5. Acceptance criteria

1. Subscription and one-time checkout modes call their correct Toss V2 SDK methods while returning no secret or billing key.
2. Billing auth success performs server-side billing-key issuance and first sandbox approval with order/amount/customer validation and exactly-once effects.
3. Admin Toss enable is honored in local/test mode, validates sandbox keys, records an audit reason, and preserves live-provider safety.
4. Local Compose and setup documentation make the localhost:3000 sandbox path reproducible, including generated `APP_SECRET_KEY` and official MCP setup.
5. Web type/tests and focused Python billing tests pass without live payment calls.

Each item maps 1:1 to the acceptance criteria in `phases/toss-subscription-sandbox/step0.md`.

## 6. Hand-off

- Interview contract: skipped and recorded because this worktree had no interview hand-off and the user supplied an explicit ordered implementation request.
- Review artifact: `/dev-kit:proposal toss-payment/subscription-sandbox`.
- Next invocation: `/dev-kit:build`.
- Build must use the step's TDD order: capture RED, implement GREEN, refactor, then run the declared verification commands.
