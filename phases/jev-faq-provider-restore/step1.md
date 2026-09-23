Status: completed
Name: document-env-vars-and-verify-wire-contract

## Read first

- `phases/jev-faq-provider-restore/step0.md` (what step0 already shipped)
- `.env.example`, `apps/web/.env.example` (existing `FAQ_OPENAI_ENABLED`/`OPENAI_*` documentation style to mirror)
- `phases/jev-cs-faq-bot/README.md` (the original feature's operational doc, to be extended, not replaced)
- `docs/proposals/reviewing/jev-typesafe-integration/idea-jev-typesafe-integration.yaml`, section "Rollout sequence when a key is issued" — step1 of this task implements step 1 of that sequence only (steps 2-4 are staging/production decisions, explicitly out of scope here)

## Task

Two independent pieces of work, both explicitly named as outstanding in the
proposal's "Review and next steps" but not yet done:

**1. Environment variable documentation.** Add `FAQ_PROVIDER`, `JEV_API_KEY`,
`JEV_API_URL`, `JEV_MODEL`, and `JEV_TIMEOUT_MS` to `.env.example` and
`apps/web/.env.example`, immediately alongside the existing FAQ block, with a
comment matching the existing style ("Server-only FAQ routing. Keep disabled
for local development and tests."). Extend `phases/jev-cs-faq-bot/README.md`
with a short section documenting the Jev alternative: how to enable it
(`FAQ_PROVIDER=jev` + `JEV_API_KEY`), that it defaults off, and that it
shares every safety/rate-limit/redaction property already documented for the
OpenAI path (the README should point at, not duplicate, that existing text).

**2. Live wire-contract verification.** A `JEV_API_KEY` is now present in the
maintainer's local `.env` (main checkout, not committed, not copied into this
worktree). Perform step 1 of the proposal's rollout sequence exactly once,
manually, outside CI: send one bounded, synthetic, non-personal question
through `createJevProvider` against the real `https://api.typesafe.ai/v1/systemone`
endpoint and confirm the response satisfies `parseJev`'s schema and
`validDistribution()`. Record only the redacted outcome (schema-valid or not,
HTTP status, latency) — never the API key, never raw response content beyond
what's needed to state pass/fail.

## Acceptance Criteria

1. `.env.example` and `apps/web/.env.example` both document all five
   `FAQ_PROVIDER`/`JEV_*` variables, consistent in style with the existing
   OpenAI block.
2. `phases/jev-cs-faq-bot/README.md` documents how to enable the Jev
   provider without duplicating the safety/rate-limit prose already there.
3. One live call against the real Jev endpoint is made and its outcome
   (schema-valid response or not; if not, the specific mismatch) is recorded
   in `phases/jev-faq-provider-restore/step1-output.json` without leaking
   the API key or full response body.
4. No API key or secret is written to any committed file, log, or test
   fixture.
5. The full web lint/test/build pipeline still passes after the
   documentation changes (no code path changed by this step, so this is a
   regression check, not new coverage).

## Verification & Status Update

```bash
pnpm --filter ai-saas-foundation-web lint
pnpm --filter ai-saas-foundation-web exec jest --runInBand tests/faq.test.ts
```

Result: `tsc --noEmit` clean; 57/57 tests still passing (no regressions from
the documentation-only changes). The one-time manual live-endpoint check
was performed outside the test suite and outside CI: HTTP 200, schema-valid,
distribution-valid, 747ms latency, `answerableNoul=0.67` for a deliberately
generic synthetic question. Full result recorded in
`phases/jev-faq-provider-restore/step1-output.json`. The API key was never
printed, logged, or written to any committed file; the one-off check script
and its driver were deleted immediately after the run.

## Don't

- Do not commit `JEV_API_KEY` or any `.env` file containing it.
- Do not send a real, personal, or tenant-derived question to the live
  endpoint — synthetic and generic only.
- Do not add the live call to the automated test suite or to CI.
- Do not change `FAQ_PROVIDER`'s default away from OpenAI.
