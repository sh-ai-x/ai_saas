# plan → build hand-off

## Plan

- Phase: `jev-cs-faq-bot`
- Branch/worktree: `feat/jev-cs-faq-bot`
- Proposal: `docs/proposals/reviewing/faq-support/jev-cs-faq-bot.html`
- Goal: expose the Drizzle FAQ catalog through a bottom-right support widget and use JEV only for bounded typed routing on deterministic misses.

## Build order

1. `step0`: implement the complete vertical slice: schema/catalog, repository, matcher, JEV port/adapter, policy, API, widget, tests, and verification.

## Required verification

- Exact/alias matches must make zero provider calls.
- JEV receives only normalized/redacted user text and bounded questions; it never supplies answer prose or arbitrary URLs.
- No provider credentials in client code, database, fixtures, or logs.
- Local/CI remain provider-free and deterministic. A live JEV key is a separate staging enablement gate.
- Do not modify auth, billing, account state, payment state, or production data.
