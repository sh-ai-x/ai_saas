Status: pending
Name: payment-mode-adapters

## Read first

- `PRD.md` §8 and REQ-16
- `docs/sot/billing/provider-adapter-architecture.md`
- `docs/sot/billing/providers/toss-payments.md`
- `docs/sot/billing/providers/lemon-squeezy.md`
- `docs/sot/billing/subscriptions-and-entitlements.md`

## Task

Connect pricing options to the existing provider-neutral payment adapters. The
server must resolve the selected pricing option and return a browser-safe
checkout handoff for mock, Toss sandbox, or Lemon Squeezy sandbox. Add admin
provider settings for safe public identifiers and provider selection. Preserve
the one-live-provider rule and distinguish one-time orders from subscriptions.

## Acceptance Criteria

- Checkout accepts an option ID and never trusts client amount/currency/mode.
- The active catalog accepts either one-time or subscription requests, never
  both simultaneously. Subscription requests can be monthly or yearly; a
  one-time request has no renewal interval.
- Provider settings expose no secret values and reject mixed live providers.
- Local mode defaults to mock and is visibly labeled; production fails closed
  without an explicit provider configuration.
- Existing Toss/Lemon Squeezy sandbox and webhook contracts remain compatible.

## Verification & Status Update

Record adapter contract tests, unauthorized admin tests, and API responses in
`step17-output.json`. Include the selected provider and environment profile in
the evidence without printing credentials.

## Don't

- Do not call Toss or Lemon Squeezy directly from browser components.
- Do not grant entitlements from a redirect alone.
- Do not enable two live payment providers in the same environment.
