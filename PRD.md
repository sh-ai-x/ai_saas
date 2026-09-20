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

# OpenAI-routed FAQ Support Bot — Minimal Cost-safe Vertical Slice

## 1. Frame

- **Goal:** Ship a bottom-right FAQ Support bot that answers catalog-backed questions deterministically and uses one bounded OpenAI Structured Output call only when fixed matching misses.
- **Target user:** A product user trying to resolve a common setup, workspace, or support question without opening a support request.
- **Situation:** The application has a Drizzle FAQ table and seed data but no API, AI routing path, or visible FAQ surface.

## 2. Decision

Use the existing `FaqProvider` port with a direct OpenAI Responses API adapter using `gpt-4o-mini` and strict JSON Schema output. LangChain/LangGraph are intentionally not added: they are orchestration libraries, not model access, and this fixed FAQ flow has no graph, tool, memory, or RAG requirement. Direct HTTP keeps the dependency and latency budget smaller.

The model returns only `faqId`, `category`, `answerable`, and `confidence`. Application code validates those fields and returns answer prose owned by the Drizzle catalog. Exact/alias matches remain zero-cost and never call OpenAI.

### Independent evidence

1. OpenAI lists GPT-4o mini as a fast, affordable small model with Structured Outputs support, Responses API support, and $0.15/$0.60 per million input/output tokens. [src:https://developers.openai.com/api/docs/models/gpt-4o-mini;ts:2026-09-20;type:primary]
2. OpenAI Structured Outputs with `text.format` and `strict: true` is designed to make the response conform to the supplied JSON Schema. [src:https://developers.openai.com/ko-KR/api/docs/guides/structured-outputs;ts:2026-09-20;type:primary]
3. The Responses API supports `store: false`, bounded `max_output_tokens`, and no tools for this stateless classification request. [src:https://developers.openai.com/api/reference/cli/resources/responses/methods/create;ts:2026-09-20;type:primary]

## 3. Cost, latency, accuracy, and safety policy

- Exact/alias match: zero provider calls.
- AI miss path: one call, at most five public FAQ candidates, no conversation history or account context.
- Output: strict schema, known FAQ ID allowlist, category check, confidence `>= .85`, answerable gate, catalog-only answer text.
- Budget: `gpt-4o-mini`, `max_output_tokens=80`, 1.5-second provider deadline, no retries, one in-flight request, 30-second circuit cooldown, and 60 API requests/minute per process.
- Privacy: normalized/redacted question, server-only `OPENAI_API_KEY`, `store:false`, no tools, no persistence, no tenant/account/payment data.
- Failure: disabled/missing key, timeout, malformed output, rate limit, provider error, low confidence, or unknown ID returns deterministic clarification/handoff.

## 4. Non-goals

1. Open-ended generated answers, RAG, embeddings, memory, attachments, or arbitrary tools.
2. Account, billing, payment, password, or ticket mutations.
3. Browser-to-provider calls or client-side provider credentials.
4. Live provider calls in local/CI; tests use mocked HTTP and the default remains provider-free.

## 5. Acceptance criteria

- **REQ-1:** Drizzle owns `faq_entries`; migration/seed data and repository tests are committed.
- **REQ-2:** Exact/alias matches make zero provider calls; misses make at most one bounded OpenAI call and never return provider-generated prose.
- **REQ-3:** `GET /api/faq` and `POST /api/faq` expose versioned validated contracts with deterministic `answer`, `clarify`, and `handoff` outcomes.
- **REQ-4:** The root layout renders a right-bottom widget with presets, free text, loading/error states, catalog-only answers, and a support CTA.
- **REQ-5:** Focused tests, typecheck, full web test/build, browser smoke, and diff checks pass without live credentials or production writes.

## 6. Operational gate

Enable only in staging first with `FAQ_OPENAI_ENABLED=true`, a server-injected `OPENAI_API_KEY`, and a measured synthetic FAQ set. Record p50/p95/p99 latency, provider-call rate, confidence calibration, correct-routing rate, false-answer rate, fallback rate, and monthly spend before production promotion. The model price and provider limits are reference data, not this product's SLO.

Phase directory remains `phases/jev-cs-faq-bot/` for continuity with the already-created plan artifacts; its implementation/provider naming is OpenAI-based.
