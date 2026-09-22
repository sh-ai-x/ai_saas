# Plan → Build Handoff

## toss-subscription-sandbox

- Phase: `toss-subscription-sandbox`
- Branch/worktree: `feat/subscription-toss-payment`
- Proposal: `docs/proposals/reviewing/toss-payment/subscription-sandbox.html`
- Goal: connect the existing subscription catalog and admin Toss enable switch to a verified Toss Payments V2 sandbox flow at localhost:3000 without real charging.
- Methodology: TDD — capture RED first, implement GREEN, refactor, then run the declared web and Python verification commands.

### Evidence-driven decisions

- Use `requestBillingAuth()` for subscription options, not `requestPayment()`.
- Keep the secret key and billing key server-side.
- Persist and validate the server-owned order, amount, currency, provider, and customer identity before the first recurring approval.
- Treat the existing idempotent order/entitlement/credit path as the settlement authority.
- Let an enabled persisted Toss setting drive local/test selection while requiring sandbox-compatible runtime keys.

### Build order

1. `step0`: implement the complete vertical slice: schema/catalog, repository, matcher, OpenAI provider port/adapter, policy, API, widget, tests, and verification.

### Required verification

```bash
pnpm --dir apps/web test
pnpm --dir apps/web lint
uv run --locked python -m unittest tests/test_payment_sandbox_api.py tests/test_billing.py tests/test_integration_contracts.py
```

### Safety boundary

Do not add live keys, real card data, or live payment calls. Production recurring scheduling, dunning, refunds, and webhook tunnel operations are explicitly deferred.

### Next hand-off

On success, continue to `/dev-kit:review` and `/dev-kit:security`; inspect the per-step two-commit protocol and verification evidence before any release action.

---

## jev-cs-faq-bot

- Phase: `jev-cs-faq-bot`
- Branch/worktree: `feat/faq-ai-provider`
- Proposal: `docs/proposals/reviewing/faq-support/jev-cs-faq-bot.html`
- Goal: expose the Drizzle FAQ catalog through a bottom-right support widget and use OpenAI Structured Outputs only for bounded routing on deterministic misses.

### Build order

1. `step0`: implement the complete vertical slice: schema/catalog, repository, matcher, OpenAI provider port/adapter, policy, API, widget, tests, and verification.

### Required evidence

- Exact/alias matches must make zero provider calls.
- OpenAI receives only normalized/redacted user text and bounded questions; it never supplies answer prose or arbitrary URLs.
- No provider credentials in client code, database, fixtures, or logs.
- Local/CI remain provider-free and deterministic. A live OpenAI key is a separate staging enablement gate.
- Do not modify auth, billing, account state, payment state, or production data.

### Safety boundary

- Exact/alias match: zero provider calls.
- AI miss path: one call, at most five public FAQ candidates, no conversation history or account context.

### Next hand-off

After build completes, run `/dev-kit:review`, `/dev-kit:security`, and `/dev-kit:ship`. Do not create or push a private remote until the review/security gates and human merge boundary are complete.

---

## proposal-to-verified-change

- Phase: `proposal-to-verified-change`
- Branch/worktree: `plan/proposal-to-verified-change-agent`
- Proposal: `docs/proposals/applied/proposal-to-verified-change-agent/idea-proposal-to-verified-change-agent.html`
- Goal: implement one bounded, evidence-backed change-assurance workflow with kernel-owned token budgets and replaceable Project Pack boundaries.

### Build order

1. `step0`: implement the complete offline vertical slice: kernel contracts, token/cache controls, repository evidence, Lang* adapter boundaries, approval/resume workflow, sandbox/delivery ports, metrics, Local Lite profile, and conformance tests.

### Safety boundary

- No legacy foundation/pricing plan artifacts remain in this product branch.
- No secrets, external credentials, arbitrary shell, provider fallback, local model, vector database, or unbounded network call.
- Local Lite must run with the deterministic fake provider and no Docker or always-on infrastructure.
- The evaluation ledger is authoritative; LangSmith is redacted telemetry/evaluation only.
- Build must leave real `step0-output.json` evidence and the two-commit protocol on the per-step branch.

### Required evidence

- Focused tests for requirements, evidence grounding, approval, resume, token exhaustion, cache behavior, redaction, prompt injection, unknown runtime, and adapter conformance.
- Exact token arithmetic and release report fields.
- `dispatch: sequential` reason from the build runner.
- No high-severity pre-build intent-integrity finding.

### Next hand-off

After build completes, run `/dev-kit:review`, `/dev-kit:security`, and `/dev-kit:ship`. Do not create or push a private remote until the review/security gates and human merge boundary are complete.