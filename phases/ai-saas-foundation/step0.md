Status: completed
Name: baseline-contracts

Read first:
- `PRD.md`
- `.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md`
- `docs/sot/architecture/system-map.md`
- `docs/sot/operations/aws-docker-deployment.md`
- `docs/setup-guides/00-local-foundation.md`

Task:
Create the smallest runnable foundation skeleton from the `mysaas` baseline. Establish the repository/module ownership map, versioned REST/SSE/event/provider contracts, environment profiles (`free-portfolio` and `aws-worker`), safe configuration validation, local Docker instructions, and deterministic contract checks. Do not add secrets or provision cloud resources.

Acceptance:
- REQ-1: A documented and executable local start/check path exists.
- REQ-5: Free and AWS worker profiles fail closed on missing or paid-only configuration.

Verification:
uv run --locked python -m lib.intent_integrity --pre ai-saas-foundation

Don't:
- Do not implement provider-specific payment behavior in the domain.
- Do not add ALB, NAT, Redis, or paid infrastructure.
- Do not copy secrets from `../mysaas`.
