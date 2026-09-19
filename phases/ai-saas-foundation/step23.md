Status: completed
Name: google-auth-verification

## Read first

- `PRD.md` §9 and REQ-19–REQ-23
- `phases/ai-saas-foundation/step20.md`
- `phases/ai-saas-foundation/step21.md`
- `phases/ai-saas-foundation/step22.md`
- `docs/sot/auth/google-oauth.md`
- `.dev-kit/ci-config.json`

## Task

Verify the Google authentication extension end to end. Run schema and
migration checks, deterministic OAuth/session contract tests, admin denial
tests, local browser smoke tests, secret scans, and a production build. Add
the detailed Markdown setup guide for Google Cloud Console redirect URIs,
runtime environment variables, Neon migration, local demo mode, and safe
verification. Leave exact evidence in the step output.

## Acceptance Criteria

- Auth schema and migration checks pass and the final migration contains all
  four identity tables with the required constraints.
- Deterministic tests cover valid local sign-in, missing production
  configuration, ordinary user/admin separation, and local sign-out. Better
  Auth owns provider callback state validation; live callback replay and code
  exchange remain a configured staging verification rather than a credential-
  free test claim.
- Browser smoke verifies landing → login → local demo/session projection and
  preserves billing/admin route behavior; console errors are zero.
- Setup documentation is imported into the web Markdown guide sidebar and
  contains no secrets or real account data.
- Limitations are explicit: local demo mode is not proof of Google production
  certification, and production requires Google Cloud Console credentials.

## Verification & Status Update

Write real command output metadata to `step23-output.json`; do not fabricate
exit codes or durations. Update the phase index only after evidence exists.

## Don't

- Do not call Google's live token endpoint from automated tests.
- Do not commit `.env.local`, client secrets, OAuth codes, or access tokens.
- Do not delete pricing, payment, or prior phase evidence.
