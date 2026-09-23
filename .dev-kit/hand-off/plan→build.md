# Plan → Build Handoff — Restore Jev as the FAQ Provider

## Baseline

The FAQ support bot from `feat/faq-ai-provider` (merged, `origin/main`) is the
baseline. This plan restores the Jev provider it originally shipped with,
behind the same `FaqProvider` port the OpenAI adapter already uses, and closes
the two documentation gaps the design record left open.

## Build order

1. `restore-jev-provider` (step0) — **already implemented and verified**
   before this plan stage began: `jev.ts` recovered from `05426b1` with both
   bugs fixed, shared timeout constant, `FAQ_PROVIDER` route conditional,
   proposal amendment, dedicated + conformance test suites. 57/57 tests
   passing, `tsc --noEmit` clean, build succeeds. This step exists in the
   phase record for traceability, not as pending build work.
2. `document-env-vars-and-verify-wire-contract` (step1) — the actual
   remaining work: `.env.example` / `apps/web/.env.example` / phase README
   documentation for `FAQ_PROVIDER` and `JEV_*`, plus one manual, one-time,
   non-CI live call against the real Jev endpoint using the `JEV_API_KEY`
   now available in the maintainer's local `.env`, to close the single
   residual risk the unit tests cannot reach (a wire-format mismatch between
   `parseJev`'s schema and the live response).

## Guardrails

- `FAQ_PROVIDER` defaults to OpenAI; nothing about this phase changes
  default behavior for an operator who does nothing.
- `JEV_API_KEY` must never be committed, logged, or written into any file
  under this worktree. The live wire-contract check reads it from the main
  checkout's `.env` at call time only.
- The live wire-contract check is manual and one-time, explicitly excluded
  from the automated test suite and from CI.
- No new abstraction (no provider-factory module) — the design record is
  explicit that this is the wrong trade at two providers.
- Nothing in this phase retunes the `confidence`/`answerable` thresholds, or
  touches the matcher, repository, schema, HTTP layer, or widget.
