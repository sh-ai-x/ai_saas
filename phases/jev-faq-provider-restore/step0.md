Status: completed
Name: restore-jev-provider

## Read first

- `PRD.md` §§1-6
- `docs/proposals/reviewing/jev-typesafe-integration/idea-jev-typesafe-integration.yaml` (the design record this step implements)
- `apps/web/lib/faq/provider.ts`, `apps/web/lib/faq/openai.ts`, `apps/web/lib/faq/service.ts`
- `apps/web/lib/faq/seed.ts` (proof that 5 of 6 seed categories are outside the archived adapter's hard-coded list)
- Archived adapter at `git show 05426b1:apps/web/lib/faq/jev.ts`

## Task

Restore `apps/web/lib/faq/jev.ts` from commit `05426b1` behind the existing
`FaqProvider` port as a config-flagged alternative to `openai.ts`. Fix both
bugs a verbatim revert would re-ship, not just one:

1. The hard-coded category list at **both** call sites — the validation set
   passed to `validDistribution()` and the model-facing `criteria` object —
   via one `categoryCriteria(candidates)` helper so the two sites cannot
   drift apart again. A category with no known human-readable label falls
   back to using its own name.
2. The `Math.min(options.timeoutMs ?? 1200, 1200)` hard clamp, replaced with
   a shared `DEFAULT_PROVIDER_TIMEOUT_MS = 5_000` constant in `provider.ts`
   that both adapters import, reconciling the two budgets instead of leaving
   them 4x apart.

Wire an inline `FAQ_PROVIDER` conditional into `route.ts` (`FAQ_PROVIDER=jev`
selects Jev; anything else, including unset, keeps today's OpenAI default
byte-for-byte). Add a record-correction amendment section to
`docs/proposals/faq-support/jev-cs-faq-bot.yaml` stating that Jev was the
original provider and the swap was a TypeSafe waitlist stopgap, not a
technical rejection. Add a dedicated Jev provider test suite plus a
parameterized conformance suite asserting both adapters share the same
behavioral contract (disabled → null, missing key → null, >5 candidates
refused, sensitive text refused, circuit breaker opens after one failure).

Introduce no new abstraction: the provider switch is an inline conditional
in the route, not a factory module.

## Acceptance Criteria

1. `apps/web/lib/faq/jev.ts` implements `FaqProvider`; a candidate whose
   category is outside `['guides','product','support','none']` (e.g. the
   seed catalog's `general`) still validates and is selectable, proving
   both call sites derive from the live candidate set.
2. Requesting a `timeoutMs` above 1200ms is honored, not silently clamped.
3. `apps/web/app/api/faq/route.ts` defaults to OpenAI when `FAQ_PROVIDER` is
   unset, byte-identical to the pre-change behavior; `FAQ_PROVIDER=jev`
   without a key degrades to the existing `clarify` fallback, never errors.
4. `docs/proposals/faq-support/jev-cs-faq-bot.yaml` carries the amendment
   section.
5. The full web lint/test/build pipeline passes, including new Jev-specific
   and conformance test cases, with zero regressions to pre-existing
   assertions (in particular `DEFAULT_OPENAI_TIMEOUT_MS === 5_000`).

## Verification & Status Update

```bash
pnpm --filter ai-saas-foundation-web lint
pnpm --filter ai-saas-foundation-web exec jest --runInBand tests/faq.test.ts
pnpm --filter ai-saas-foundation-web build
```

Result: `tsc --noEmit` clean; **57/57 tests passing** (35 pre-existing + 12
dedicated Jev tests + 10 conformance tests); production build succeeds.
Manually verified via a local dev server on port 3000: default (no
`FAQ_PROVIDER`) behaves byte-identically to before; `FAQ_PROVIDER=jev` with
no key degrades to `clarify`, never a 500. Full command output and file
diff recorded in `phases/jev-faq-provider-restore/step0-output.json`.

## Don't

- Do not remove, deprecate, or disable the OpenAI adapter.
- Do not retune the `confidence`/`answerable` thresholds at `service.ts:16`.
- Do not add a provider-factory module or any other new abstraction.
- Do not touch the matcher, repository, catalog schema, HTTP rate
  limiting/logging, or the widget.
