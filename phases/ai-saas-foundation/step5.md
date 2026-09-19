Status: completed
Name: docker-daemon-local-verification

Read first:
- `PRD.md`
- `.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md`
- `docs/proposals/pending/ai-saas-foundation/msa-foundation.yaml`
- `phases/ai-saas-foundation/step4.md`
- `https://github.com/sh-ai-x/ai_saas/issues/3`
- `https://github.com/sh-ai-x/ai_saas/pull/2`

Task:
Complete the no-cloud local verification path and record Docker availability
without changing the free-tier cost boundary or introducing paid
infrastructure. The host-local runtime must be usable even when Docker
Desktop is not running; Docker build/start is an additional environment check.

Acceptance:
- `uv run --locked python scripts/local-smoke.py` succeeds and exercises auth, admin,
  payment webhook/ledger, durable run execution, and SSE replay.
- `docker compose --file docker/dev/compose.yaml config` succeeds when the
  Docker CLI is installed; a stopped daemon is recorded as blocked rather than
  hidden or worked around with paid infrastructure.
- When the local profile is started, health/startup evidence is recorded and
  no secrets are written to logs or source.

Verification:
```bash
uv run --locked python scripts/local-smoke.py
uv run --locked python scripts/record-step-outputs.py --step 5
```

Do not:
- Do not use `git reset --hard`, force-push, or auto-merge.
- Do not add ALB, NAT, Redis, always-on ECS, or paid Cloudflare/Vercel plans.
- Do not copy secrets into `.env`, logs, fixtures, or Docker layers.
