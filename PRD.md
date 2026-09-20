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

---

# JEV-routed FAQ Support Bot — Minimal Cost-safe Vertical Slice

## 1. Frame

- **Goal:** Ship a bottom-right FAQ Support bot that answers catalog-backed questions deterministically and uses JEV only as a bounded category/FAQ router when fixed matching misses.
- **Target user:** A product user trying to resolve a common setup, login, pricing, or agent-run question without opening a support request.
- **Situation:** The application has a Drizzle FAQ table and seed data but no API, JEV decision path, or visible FAQ surface, so users cannot discover or use the catalog.

## 2. Validate

### Independent evidence

1. **Existing product signal:** `faq_entries` is already the intended data boundary in the working implementation direction; the missing piece is the API/UI path that consumes it.
2. **Provider signal:** TypeSafe describes Jev as a typed decision API with `state`, typed questions, probabilities, and confidence, and explicitly positions it for routing rather than string generation. [src:https://typesafe.ai/blog/introducing-system-one-models-and-jev;ts:2026-09-20;type:primary]
3. **Workflow signal:** TypeSafe's workflow guidance recommends decomposing work into narrow typed questions and programmatic rules, while its customer-service example includes safety checks and handoff states. [src:https://evals.typesafe.ai/;ts:2026-09-20;type:primary] [src:https://evals.typesafe.ai/customer_service;ts:2026-09-20;type:primary]
4. **Risk signal:** The vendor API is early access and external; TypeSafe's privacy and contract materials require server-side credential handling and a separate privacy/usage review. [src:https://typesafe.ai/legal/privacy-policy;ts:2026-09-20;type:primary] [src:https://typesafe.ai/legal/mca;ts:2026-09-20;type:primary]

### Value score

- `LTV_per_user`: 240 value units per retained self-service user
- `reachable_users_year1`: 25 initial product users
- `total_cost`: 1,200 value units of implementation and low-volume infrastructure
- `value_score = (240 × 25) / 1,200 = 5.0`

### Ambiguity

- `ambiguity_score: 3/10`
- Locked decisions: Drizzle owns the catalog; exact/alias matching is the zero-cost path; JEV is one-call typed routing only; code owns answer text; low confidence and provider failure produce fixed fallback; the local default is deterministic and provider-free.
- Implementation gate retained: live JEV access, current account limits, retention/region terms, and workload calibration must be verified before enabling JEV in staging or production.

## 3. Non-goals

1. **Open-ended generated answers:** JEV must not author prose; this prevents hallucinated or stale support instructions. If requested, create a separate answer-generation security and evaluation plan.
2. **Account, billing, or ticket mutations:** The MVP is read-only and cannot reset passwords, change plans, refund charges, or create tickets. If requested, route to a separate authenticated workflow with idempotency and human approval.
3. **RAG, embeddings, memory, attachments, and arbitrary tools:** The MVP uses a small catalog and bounded typed questions to control token cost and attack surface. If coverage is insufficient, first expand the catalog and labeled evaluation set.
4. **Live-provider dependency in local/test:** Local and CI use deterministic fixtures; a live JEV key is an explicit staging gate, never a hidden test prerequisite.

## 4. Phase plan

Phase directory: `phases/jev-cs-faq-bot/`

This phase is one shippable vertical slice so the build runner can produce an auditable implementation branch without pretending that independent steps share unmerged worktrees.

| Step | Name | Dependency | Outcome |
|---:|---|---|---|
| 0 | vertical-faq-support-bot | none | Drizzle FAQ catalog, layered router/JEV adapter/policy, versioned API, bottom-right widget, tests, and verification evidence |

The authoritative step state is `phases/jev-cs-faq-bot/index.json`.

## 5. Acceptance criteria

- **REQ-1:** Drizzle owns `faq_entries`; migration/seed data and repository tests are committed, and no provider call is made for exact/alias matches.
- **REQ-2:** The server-side JEV adapter sends only bounded redacted state, makes at most one call per miss, validates typed answers/confidence, and maps only known FAQ IDs to catalog content.
- **REQ-3:** `GET /api/faq` and `POST /api/faq` expose versioned validated contracts with deterministic `answer`, `clarify`, and `handoff` outcomes and bounded rate/timeout/fallback behavior.
- **REQ-4:** The root layout renders a right-bottom FAQ widget that supports presets and free text, never exposes provider secrets, and shows a fixed support CTA when the bot abstains.
- **REQ-5:** Focused tests, typecheck, full web test/build, and diff checks pass without live provider credentials or production writes.

## 6. Handoff to build

The plan is ready for `/dev-kit:build` in the single-step phase. The design record is `docs/proposals/reviewing/faq-support/jev-cs-faq-bot.html`. Build must keep JEV optional and fail closed, preserve the existing auth/billing boundaries, and record all verification evidence before handoff to review.

Sources used for the plan: TypeSafe's Jev launch description and API shape, TypeSafe workflow evaluation guidance, customer-service handoff pattern, privacy policy, and master customer agreement. Vendor speed/cost figures are planning context only; this phase must measure its own latency, call count, confidence behavior, and fallback rate.
