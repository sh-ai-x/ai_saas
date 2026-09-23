# PRD — Restore Jev as the FAQ Provider

## 1. Frame

- Goal: Restore the archived `jev.ts` FAQ provider behind the existing `FaqProvider` port as a config-flagged alternative to `openai.ts`, fix the two bugs a verbatim revert would re-ship, document why OpenAI was chosen, and document the environment variables so the switch is operable.
- Target user: The repository maintainer / operator who currently cannot tell from any file why the FAQ bot routes through OpenAI instead of Jev, and who has no config path back to Jev once TypeSafe/Jev API access clears its waitlist.
- Situation: A customer-facing FAQ support bot is merged on `origin/main`. Jev was its original provider (`05426b1`/`03a1faf`), then deleted outright and replaced with OpenAI (`726dcaa`) with no rationale recorded anywhere in the repository. The provider port (`apps/web/lib/faq/provider.ts`) was kept identical between adapters specifically so this restoration would be cheap.

## 2. Validate

### Independent evidence

1. **Git history** — `apps/web/lib/faq/jev.ts` does not exist on `origin/main` (`git ls-tree origin/main -- apps/web/lib/faq/jev.ts` returns nothing); it was introduced with the feature in `05426b1`/`03a1faf` and deleted in `726dcaa fix(faq): replace JEV with OpenAI structured router`, recoverable verbatim via `git show 05426b1:apps/web/lib/faq/jev.ts`. Source: repository commit history. Date: 2026-09-22.
2. **Source code** — `apps/web/lib/faq/openai.ts:94` declares `answerable` as a JSON Schema boolean and `:45` maps it to `1|0`, so the `answerable >= 0.9` gate at `apps/web/lib/faq/service.ts:16` is degenerate (equivalent to `=== 1`) under the currently active provider; Jev's Noul (`jev.ts:8,17` at `05426b1`) is the only configuration where that existing threshold does real work. Source: static code reading. Date: 2026-09-22.
3. **Maintainer statement** — the repo owner stated directly in conversation on 2026-09-22 that TypeSafe/Jev API access is pending waitlist approval, and that the OpenAI swap was an access-availability stopgap, not a technical or design rejection of Jev; this is recorded in no file in the repository prior to this PRD. Source: direct conversation, not independently verifiable from repo artifacts alone — recorded here as the PRD's own evidence trail. Date: 2026-09-22.

### Value score

This is an internal engineering/config change, not a monetized user-facing feature, so `value_score` is framed as engineering cost avoided rather than user LTV:

- The archaeological recovery performed once in this cycle (locating the deleted commit, diffing it against the current adapter, finding and fixing two bugs) took real engineering time. Estimate: 2 hours at $100/hr = $200 per recurrence.
- Without a config flag and a written record, every future "should we use Jev?" conversation repeats this recovery from scratch. Conservatively 3 such recurrences avoided over the next year (waitlist status changes, a new engineer asks, a future audit) = $600 value.
- Cost of this change: recovery + 2 bug fixes + provider-conformance tests + docs, already performed = ~1 hour additional engineering = $100 (the recovery cost is counted once, in the value side, not double-counted in cost).

`value_score = $600 / $100 = 6.0` — PASS (threshold ≥ 3.0).

### Ambiguity loop

`ambiguity_score: 10 → 6 → 3 → 2` — PASS (threshold ≤ 3).

- 10: scope was completely open — "use Jev somewhere in this repo" with no concrete integration point identified.
- 6: repository investigation (this conversation, 2026-09-22) identified the FAQ router as the one spot where Jev was already built, shipped-adjacent, and only sidelined by an access gate — narrowing from "where could Jev apply" to "restore what was already there."
- 3: iterative proposal refinement (draft → cheapest-slice trim → cons/limitations resolution → third-bug documentation) converged the scope to exactly 5 files, explicitly deferring ranking and email-escalation as separate follow-on proposals.
- 2: this PRD's own gate-2 cycle confirms no remaining open design question — the only two items still explicitly open for reviewer judgment (5000ms vs a tighter Jev-specific timeout; inline conditional vs factory module) are already resolved with stated rationale in the proposal, not blocking implementation.

## 3. Non-goals

1. **Removing, deprecating, or disabling the OpenAI adapter.** Rationale: OpenAI remains the default and fully supported; this is a restoration, not a replacement. Breach response: reject any request to remove OpenAI as part of this phase; scope a separate deprecation proposal only after Jev has production traffic evidence.
2. **Retuning the `confidence`/`answerable` thresholds at `service.ts:16`, or any calibration work.** Rationale: `confidence` and `answerable` mean materially different things across the two adapters, and retuning without real Jev traffic would be guessing. Breach response: defer to a follow-on proposal once the rollout sequence's parallel-run step produces real distribution data.
3. **The FAQ widget's unbounded button list (ranking) and the human-notification gap on a genuine miss (email escalation).** Rationale: both are real, independent problems already documented in the proposal's "Deferred" section, worth doing whether or not Jev is ever enabled — bundling them would have made a cheap, reversible change expensive to review. Breach response: defer each to its own proposal; do not fold either into this phase's steps.
4. **A provider-factory abstraction module.** Rationale: at exactly two adapters, a factory file is more indirection than the ternary it would replace — cost optimization here means implementation/comprehension cost, not only runtime cost. Breach response: reconsider only if and when a third FAQ provider is proposed.

## 4. Phase plan

Phase index: `phases/jev-faq-provider-restore/index.json`

### Step 0 — restore-jev-provider

Recover `apps/web/lib/faq/jev.ts` from commit `05426b1` behind the existing `FaqProvider` port, fix both archived bugs (category derivation at both call sites; timeout clamp reconciled to a shared `DEFAULT_PROVIDER_TIMEOUT_MS`), wire an inline `FAQ_PROVIDER` env conditional into `route.ts` defaulting to OpenAI, add the record-correction amendment to `docs/proposals/faq-support/jev-cs-faq-bot.yaml`, and add both a dedicated Jev test suite and a cross-provider conformance suite. **Status: completed** — implemented and verified before this PRD was written; this step documents work already done, not work still pending.

### Step 1 — document-env-vars-and-verify-wire-contract

Document `FAQ_PROVIDER` and the `JEV_*` environment variables in `.env.example`, `apps/web/.env.example`, and the phase README (the proposal's own "Review and next steps" lists this as required, not yet done). Then perform step 1 of the proposal's stated rollout sequence: verify the live wire contract against the real `api.typesafe.ai` endpoint exactly once, manually, outside CI, using the `JEV_API_KEY` now available in the maintainer's local `.env`, and record the (redacted, non-secret) outcome.

## 5. Acceptance criteria

1. `apps/web/lib/faq/jev.ts` exists, implements `FaqProvider`, derives its category set from the live candidate list at both the validation and model-criteria call sites, and uses the shared `DEFAULT_PROVIDER_TIMEOUT_MS` instead of a hard clamp.
2. `apps/web/app/api/faq/route.ts` selects between `createJevProvider` and `createOpenAiProvider` via `process.env.FAQ_PROVIDER`, defaulting to OpenAI when unset.
3. `docs/proposals/faq-support/jev-cs-faq-bot.yaml` carries an amendment section stating why OpenAI was chosen over Jev.
4. `FAQ_PROVIDER`, `JEV_API_KEY`, `JEV_API_URL`, `JEV_MODEL`, and `JEV_TIMEOUT_MS` are documented in both `.env.example` files and the phase README, consistent with the existing `FAQ_OPENAI_ENABLED`/`OPENAI_*` documentation style.
5. The full web test/lint/build suite passes with zero regressions, and a one-time manual live-wire-contract check against the real Jev endpoint is performed and its outcome recorded without leaking the API key or any user question content into a committed file.

Each item maps 1:1 to the acceptance criteria in `phases/jev-faq-provider-restore/step0.md` and `step1.md`.

## 6. Hand-off

- Interview contract: skipped and recorded because this worktree had no interview hand-off and the design was already fully settled through the proposal at `docs/proposals/reviewing/jev-typesafe-integration/idea-jev-typesafe-integration.yaml` (iteratively reviewed with the maintainer across multiple rounds: draft → cheapest-slice trim → cons/limitations resolution → third-bug documentation).
- Review artifact: `docs/proposals/reviewing/jev-typesafe-integration/idea-jev-typesafe-integration.html`.
- Next invocation: `/dev-kit:build` (this PRD documents step0 as already built/verified and step1 as the remaining work to execute).
- Build must use the step's TDD order for step1: capture RED where a new assertion is meaningful, implement GREEN, refactor, then run the declared verification commands.
