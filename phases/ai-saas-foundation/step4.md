Status: completed
Name: low-cost-deployment-observability

Read first:
- `PRD.md`
- `docs/sot/operations/aws-docker-deployment.md`
- `docs/sot/architecture/system-map.md`
- `docs/sot/verification/release-and-incident.md`
- `phases/ai-saas-foundation/step3.md`

Task:
Finish the free portfolio and AWS low-cost worker profiles. Add quota counters and pause-on-limit behavior, sampled OpenTelemetry with redaction, CI checks, Docker/local verification, and a Fargate Spot RunTask deployment contract using minimal ARM resources, public-subnet outbound access, no ALB/NAT, and no inbound worker rules. Add evaluator scenarios and evidence capture for auth, admin, payment replay, ledger concurrency, run recovery, and profile boundaries.

Acceptance:
- REQ-5: Free mode never silently creates paid resources; AWS worker mode is interruptible, checkpointed, and auditable.

Verification:
python3 -m lib.intent_integrity --pre ai-saas-foundation

Don't:
- Do not provision or require paid Cloudflare/Vercel plans, ALB, NAT, or always-on ECS.
- Do not log secrets, OAuth codes, payment payloads, or raw sensitive prompts.
- Do not claim commercial SLA or multi-AZ availability for the low-cost profile.
