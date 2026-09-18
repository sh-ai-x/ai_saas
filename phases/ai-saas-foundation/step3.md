Status: pending
Name: run-worker-streaming

Read first:
- `PRD.md`
- `.dev-kit/hand-off/sot-harness-ai-saas-msa-20260918.md`
- `docs/sot/agent/runtime-and-tools.md`
- `docs/sot/agent/observability-and-evaluation.md`
- `phases/ai-saas-foundation/step2.md`

Task:
Implement the durable run contract and the low-cost execution path. Add run state transitions, idempotency, credit reservation before model work, bounded Inngest workflow execution, persisted checkpoints/events, SSE streaming with replay/reconnect, and an optional worker boundary suitable for Fargate Spot interruption. Keep worker retries safe and make cancellation/approval states explicit.

Acceptance:
- REQ-4: Runs do not double-spend credits, can replay stream state, and recover after an interrupted worker.

Verification:
python3 -m lib.intent_integrity --pre ai-saas-foundation

Don't:
- Do not perform unbounded model calls or rely on in-memory worker state.
- Do not stream sensitive prompts or payment payloads without redaction policy.
- Do not couple the browser directly to a worker process.
