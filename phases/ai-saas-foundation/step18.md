Status: pending
Name: pricing-verification

## Read first

- `PRD.md` §8
- `phases/ai-saas-foundation/step15.md`
- `phases/ai-saas-foundation/step16.md`
- `phases/ai-saas-foundation/step17.md`
- `.dev-kit/ci-config.json`

## Task

Verify the schema-first pricing implementation end to end. Run typecheck,
migration/config checks, API contract tests, and a browser smoke path across
landing, user app, admin pricing, provider settings, and checkout mode choice.
Fix only failures within this phase's ownership and leave exact evidence in
the step output. Keep the local no-secret/no-paid-infrastructure profile
working.

## Acceptance Criteria

- All relevant tests and typechecks pass with quoted exit codes.
- The committed migration matches the Drizzle schema and is idempotent or
  safely guarded according to the project migration convention.
- Landing → app → admin → pricing mode selection is browser-verifiable.
- No secret, token, or database URL appears in source, output, or screenshots.
- Limitations are explicit: local fallback is not a production database and
  sandbox checkout is not live entitlement proof.

## Verification & Status Update

Write real command output metadata to `step18-output.json`; do not fabricate
duration or exit code values. Update the phase index only after evidence is
available.

## Don't

- Do not skip verification because the local database is unavailable.
- Do not deploy paid infrastructure as part of this step.
- Do not delete prior phase evidence.
