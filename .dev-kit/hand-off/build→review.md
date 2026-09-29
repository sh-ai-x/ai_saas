# build → review hand-off

- Phase: `admin-pricing-landing-sync`
- Result: completed after the harness runner's Codex subprocess became unresponsive; the planned steps were completed manually in the same isolated worktree with the runner's sequential classification preserved.
- Step 0: RED captured in `step0-output.json` before production changes.
- Step 1: GREEN isolated PostgreSQL contract and root-cause fix captured in `step1-output.json`.
- Step 2: migration, integration, full test, lint, build, and code-sanity evidence captured in `step2-output.json`.
- Next action: review the diff, then create a PR from `plan/admin-pricing-landing-sync`.

## Toss subscription sandbox build

- Phase: `toss-subscription-sandbox`
- Branch/worktree: `feat/subscription-toss-payment`
- Result: completed via manual fallback after the delegated Codex subprocess produced no output; no code was created by that subprocess.
- Evidence: `phases/toss-subscription-sandbox/step0-output.json`
- Web: `pnpm lint` exit 0; `pnpm test` exit 0; 8 suites passed, 33 tests passed, 3 skipped.
- Python: focused billing unittest exit 0; 22 tests passed.
- Compose: `docker compose ... config --quiet` exit 0; `git diff --check` exit 0.
- Runtime note: local HTTP E2E and direct `localhost:3000` route probes were blocked by slow Next first-route compilation/timeouts before assertions; no Toss API request was made. Start the app with the setup guide's generated secret and test keys for manual browser verification.
- Next action: run `/dev-kit:review` and `/dev-kit:security` before release.

## Profile subscription lifecycle build

- Phase: `profile-subscription`
- Branch/worktree: `plan/profile-subscription` / `.worktrees/profile-subscription`
- Result: completed in the isolated worktree after the delegated runner was unavailable; implementation and verification were completed manually with the planned step boundaries preserved.
- Web: `pnpm --dir apps/web lint`, `pnpm --dir apps/web test`, and `pnpm --dir apps/web build` pass. The focused profile test covers period-end cancellation/resume and usage idempotency.
- Python: focused billing, payment sandbox, and integration contract tests pass.
- Migration gate: staging static preflight passes with 8 migrations, TLS/direct-connection checks, and no destructive SQL; no database connection or production write was performed.
- Scope: Neon/Drizzle lifecycle migration, Toss renewal scheduler with grace/expiry, server-owned token usage projection, authenticated profile cancellation/resume UI, and admin subscription directory.
- Operational note: Toss recurring billing is merchant-scheduled; the renewal route is protected by `BILLING_CRON_SECRET`. No production migration or live charge was run.
- Next action: run `/dev-kit:review` and `/dev-kit:security`, then rehearse migration and scheduler behavior in staging.
