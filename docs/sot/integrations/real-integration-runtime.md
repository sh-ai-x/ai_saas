---
doc_id: real-integration-runtime
domain: integrations
purpose: Define the API-first runtime boundary for real Google, sandbox payment, and Agent provider connections.
read_when:
  - enabling Google OAuth credentials
  - selecting Toss or Lemon Squeezy sandbox
  - adding an external Agent model provider
  - changing integration setup guides or verification gates
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../auth/google-oauth.md
  - ../billing/provider-adapter-architecture.md
  - ../agent/model-routing-and-cost.md
source_of_truth: contract
owner: platform-integrations
last_reviewed: 2026-09-19
change_impact: high
---

# Real integration runtime

## Boundary

The local Python composition root owns OAuth code exchange, provider secrets,
payment confirmation, raw webhook verification, model API calls, idempotency,
and ledger/checkpoint effects. The Next.js app owns only presentation, guide
navigation, and same-origin proxying. Browser code never calls Google, Toss,
Lemon Squeezy, OpenAI, Anthropic, or Gemini directly.

## Selection rules

- `AUTH_PROVIDER=local-mock` is the no-credential default;
  `AUTH_PROVIDER=google` requires client ID, server secret, and exact redirect.
- `PAYMENT_PROVIDER` selects one of `mock`, `toss`, or `lemon-squeezy`.
  `PAYMENT_SANDBOX=true` is required outside production; mock is forbidden in
  production. Both live providers cannot be configured together.
- `AGENT_PROVIDER=local` is deterministic. External providers require a
  runtime API key plus explicit model, output, and timeout bounds.
- Neon PostgreSQL is the durable cloud database baseline. The linked
  `production` branch receives the repository policy from `neon.ts`; `.neon`
  and `.env.local` remain ignored. The free local profile may use disposable
  local storage and must not require Neon credentials to run.

## API sequence

```text
auth start -> provider callback -> server session cookie
order create -> provider checkout/confirm -> signed normalized event -> ledger
agent execute -> reserve -> checkpoint -> provider call -> commit -> SSE replay
```

Every external effect has a stable idempotency key. A duplicate callback,
payment event, or Agent retry cannot create a second local effect.

## Verification

Deterministic HTTP fixtures run before sandbox credentials are used. They cover
Google issuer/audience/expiry/email checks, payment amount/signature/dedup,
model response normalization, configuration fail-closed behavior, and secret
redaction. Setup guides are authored as Markdown in
`apps/web/content/guides/*.md` and imported at Next.js build time with
`asset/source`. The browser receives the imported source as a read-only,
line-numbered Markdown editor; it never reads a runtime filesystem or provider
secret. The operator-facing copy is mirrored under `docs/setup-guides/`, and
the parser derives sidebar metadata and step previews from the imported
document. The product landing/operator console remains at `/`; the guide
editor is a separate `/guides` route. Its payment group has separate Toss and
Lemon Squeezy child documents so provider semantics are not collapsed into one
ambiguous setup page. Its database group has a separate Neon PostgreSQL child
document covering authentication, linking, policy deploy, env injection, and
read-only verification.
