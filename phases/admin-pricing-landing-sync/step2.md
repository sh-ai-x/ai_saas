Status: pending
Name: pricing-sync-verification

## Read first

- `PRD.md` §§4–5 and AC-2/AC-3
- `phases/admin-pricing-landing-sync/step0.md`
- `phases/admin-pricing-landing-sync/step1.md`
- `.dev-kit/ci-config.json`
- `apps/web/package.json`
- `docker/prod/compose.yaml`

## Task

Verify the full pricing consistency path with independent layers. Use a dedicated PostgreSQL test database or the project’s local compose database, apply the committed migrations, exercise an admin update, and confirm the database rows, admin API, public API, and landing render agree. Then run the full web quality gates and inspect the diff for code sanity.

The verification must make cache behavior observable rather than relying only on an HTTP status. Include the exact edited value and option identity in the evidence, prove that stale omitted options are absent, and prove that the landing page reads the active billing mode projection.

## Acceptance Criteria

- The real-PostgreSQL consistency test passes without using the local in-memory fallback.
- The complete web test suite passes, including existing auth, pricing, checkout, and admin authorization tests.
- Web lint, typecheck, and production build pass with no new warnings treated as failures.
- A code-sanity review reports only scoped files, one canonical pricing read model, no secret/config leakage, and no unrelated refactor.

## Verification & Status Update

Run and record the exact commands and exit codes for migration/config validation, focused integration tests, full web tests, lint, typecheck, and production build. Record test counts and any environment prerequisite explicitly in `phases/admin-pricing-landing-sync/step2-output.json`.

## Don't

- Do not call external payment providers or Google OAuth during verification.
- Do not use a shared production or developer database that can be damaged by test data.
- Do not mark the step complete from a sub-agent exit code alone; include independent command output.

