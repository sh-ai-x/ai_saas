Status: completed
Name: hardening-test-suite

## Scope

Add executable regression tests for the admin-controlled pricing catalog and
provider-neutral payment adapters. The suite must exercise the business rule
that the public catalog exposes exactly one billing mode at a time.

## Test coverage

- Repository invariants: exclusive catalog mode, `$290` annual subscription,
  `$79` one-time product, audit-reason requirements, option interval/amount
  validation, and live-provider conflict prevention.
- API contracts: public catalog status/body, admin authorization, mode switch,
  subscription checkout rejection under one-time policy, one-time checkout
  creation, unknown option rejection, and provider settings.
- Adapter contracts: mock checkout, Toss client-side context, Lemon Squeezy
  sandbox URL/custom order context, and missing runtime configuration failures.
- Build gates: TypeScript, Drizzle schema check/generation, and production
  Next.js build.

## Acceptance

- Web tests are executable with `pnpm --filter ai-saas-foundation-web test` and included in `pnpm --filter ai-saas-foundation-web test:all`.
- Tests do not require paid infrastructure or provider secrets.
- Production code continues to fail closed when `DATABASE_URL` is absent in
  production; test mode explicitly uses the local seed repository.
