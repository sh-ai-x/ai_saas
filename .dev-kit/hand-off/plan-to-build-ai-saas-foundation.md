# Plan → Build Handoff — AI SaaS Foundation

**Session:** `ai-saas-foundation`
**Phase:** `ai-saas-foundation`
**Profile:** free portfolio by default; optional AWS Low-Cost Worker Mode

## Scope

Build the foundation from `PRD.md` in dependency order. Preserve the ignored
reference SOT under `docs/sot/`. The first deployable slice is a modular
monolith with logical MSA ownership. The optional AWS path is worker-only:
Fargate Spot, 0.25 vCPU/0.5 GB ARM, no ALB/NAT, no inbound worker rules,
checkpointed and retryable execution.

## Steps

1. `baseline-contracts`
2. `identity-tenant-admin`
3. `billing-adapters-ledger`
4. `run-worker-streaming`
5. `low-cost-deployment-observability`
6. `docker-daemon-local-verification` — follow-up tracked in [Issue #3](https://github.com/sh-ai-x/ai_saas/issues/3), blocks final local Docker evidence before human merge of [PR #2](https://github.com/sh-ai-x/ai_saas/pull/2)
7. `pricing-data-model` — Drizzle/Neon schema and normalized catalog first
8. `public-app-admin-surfaces` — separate landing, user app, and admin console
9. `payment-mode-adapters` — one-time/subscription checkout through adapters
10. `pricing-verification` — API, schema, and browser evidence

The current build worktree is `plan/admin-pricing-foundation`. Steps 15–18 are
the active extension; they depend on the completed Neon and sandbox handoff
steps above.

## Build constraints

- Read the SOT and the proposal before each step.
- Keep provider SDKs behind billing adapters.
- Keep tenant authorization and ledger effects server-side and auditable.
- Do not add paid Cloudflare/Vercel assumptions, ALB, NAT, Redis, or always-on
  ECS resources.
- Do not write secrets or raw sensitive payloads into source, logs, traces, or
  fixtures.

## Required evidence

- Local contract/configuration check.
- Google callback and tenant/admin denial/audit checks.
- Provider signature/replay/mock and ledger concurrency checks.
- Run reservation, checkpoint, SSE replay, and interruption recovery checks.
- Free quota pause and AWS worker profile boundary checks.

## Follow-up hand-off

The implementation and hosted CI are green. The remaining local-only check is
blocked by an unavailable Docker daemon in the previous session. Continue at
`step5.md` after starting Docker Desktop, Colima, or an equivalent daemon.
Do not merge PR #2 until Issue #3 has attached local `docker info`, image-build,
and compose verification evidence.
