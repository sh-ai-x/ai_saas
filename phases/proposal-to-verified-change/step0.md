# step0.md

## Status
pending

## Read first

Read the approved design context in the prompt and the repository's `AGENTS.md` / `CLAUDE.md` pointers before editing. Implement one runnable vertical slice of the Proposal-to-Verified-Change Agent on top of the existing Python foundation. Keep the worktree self-contained and offline-testable: no API keys, Docker daemon, local model server, external network, or provider fallback.

## Task

Implement a production-shaped but lightweight Python vertical slice with these layers and ownership boundaries:

1. **Product-neutral kernel contracts** in a new `agent_platform/` package. Use stdlib dataclasses/typing and SQLite where practical. Define typed requirement, evidence reference, plan, run lifecycle, approval, usage, evaluation, adapter, and delivery records. Kernel-owned services must enforce tenant scope, idempotency, append-only event recording, checkpoint/resume, token budgets, content-addressed context caching, redaction, and fail-closed terminal states.
2. **Token budget contract**: implement the Local Lite ceilings exactly: plan-only `20_000` total model tokens (`2_000 + 9_000 + 9_000`), verify `41_000` maximum including a patch retry (`20_000 + 16_000 + 5_000`), per-call input `8_000`, five primary model calls plus one bounded retry. Record exact versus estimated provider usage, cache hit/miss, retrieval expansion, budget decisions, and return `quota_paused` or `budget_exceeded` without ever returning verified after exhaustion.
3. **Replaceable Project Pack** under `project_packs/proposal_to_verified_change/`. It must parse a proposal into structured requirements, retrieve only authorized repository paths/symbols using a deterministic filesystem index, emit line/hash evidence, generate a plan with evidence references, and degrade unknown runtimes to `plan_only`. The kernel must import ports/interfaces only; the pack must not write kernel tables directly.
4. **LangChain boundary** under `services/agent_orchestrator/`: provide a provider-neutral structured model port and prompt/context adapter. If LangChain packages are unavailable, the deterministic fake provider must work without import errors; if installed, the integration point must be explicit and typed. Do not hide auth, billing, token authority, or final success in LangChain.
5. **LangGraph boundary** under `services/agent_orchestrator/`: implement an explicit state graph or graph-compatible workflow with nodes `intake`, `profile_validate`, `inventory`, `retrieve`, `analyze`, `plan`, `human_approval`, `patch`, `test`, `evaluate`, `report`. Checkpoint state must be separate from the product run ledger. Approval must interrupt/resume and high-impact actions must never run without a valid approval token.
6. **LangSmith boundary** under `services/observability/`: add a redacted trace/evaluator adapter with optional LangSmith client integration and a deterministic no-network fallback. Raw source, secrets, prompts, credentials, and unredacted user data must not be sent. LangSmith cannot decide permissions, billing, or user-visible completion.
7. **Sandbox and delivery ports** under `services/sandbox_worker/` and `services/delivery_gateway/`: implement allowlisted paths, command/resource/network policy, deterministic patch/test simulation, and a signed delivery request object. No arbitrary shell, merge, deploy, ambient credential, or model-generated network destination.
8. **Control/runtime profile surfaces** under `services/control_api/` and `infra/profiles/local-lite/` plus `infra/nginx/`: provide a small local API/service facade, Local Lite configuration with at most two long-lived-process declarations, SQLite state, remote/fake provider mode, and Nginx route/SSE configuration without requiring those services to run in tests.
9. **Metrics/evaluation** under `services/evaluation/`: implement exact formula helpers and a machine-readable release report for requirement coverage, evidence precision, invalid references, unsupported claims, latency, token usage, cache hit rate, budget overrun, cost, approval bypass, secret leakage, prompt injection, and terminal-state consistency. Include sample count and `insufficient_sample`; never turn a zero denominator into a pass.
10. **Tests and documentation**: add focused contract/unit/integration/security tests for normal, incomplete, invalid-reference, prompt-injection, budget-exhaustion, approval-bypass, cache, resume, redaction, and unknown-runtime cases. Add a concise README for running the fake-provider Local Lite workflow and explain the LangChain/LangGraph/LangSmith boundaries. Do not add a generic chatbot, swarm, vector database, or dependency on external credentials.

Favor a small, composable implementation over framework ceremony. Optional third-party imports must be isolated behind adapters. Keep source paths stable and make future Project Pack replacement possible by deleting the current pack and running kernel conformance tests.

## Acceptance Criteria

- [ ] `python3 -m pytest -q tests/test_proposal_verified_change_agent.py` passes with focused tests covering requirements REQ-1 through REQ-5.
- [ ] A fake-provider plan-only run emits typed requirements, valid evidence paths/line ranges/hashes, a plan, token usage, cache events, and a persisted release report; an invalid reference cannot be verified.
- [ ] A verify run pauses at approval, resumes only with a scoped approval token, records checkpoint state separately from the product ledger, and rejects unauthorized side effects, prompt injection, secret leakage, and unknown runtime execution.
- [ ] Token arithmetic is enforced and tested: plan-only max `20_000`, verify max `41_000`, per-call input max `8_000`, max five primary calls plus one retry, `budget_overrun_rate=0`, and exhaustion returns `quota_paused` or `budget_exceeded`.
- [ ] Kernel conformance tests pass without the Proposal Project Pack installed; the Project Pack imports kernel ports only; optional LangChain/LangGraph/LangSmith dependencies are not required for the deterministic test profile.
- [ ] `infra/nginx/` and `infra/profiles/local-lite/` declare the minimal MSA/local boundaries without requiring Nginx, Docker, PostgreSQL, Redis, Kafka, vector DB, or a local model on an 8GB MacBook Air.

## Verification & Status Update

Run these commands from the step worktree and include their real output in the step result:

```bash
python3 -m pytest -q tests/test_proposal_verified_change_agent.py
python3 -m compileall -q agent_platform services project_packs
```

Before finishing, review the diff for secrets, unbounded model/tool loops, hidden network calls, and accidental edits outside the declared vertical slice. If an external credential, missing dependency, or safety decision is required, emit `<!-- status: blocked -->` with the exact reason instead of fabricating completion. Otherwise report the commands, test count, and remaining limitations.

## Don't

- Do not edit or restore legacy foundation/pricing proposal documents.
- Do not alter existing authentication, billing, or production deployment behavior unrelated to this product slice.
- Do not add real provider SDK credentials, network calls, Docker requirements, local LLM serving, vector infrastructure, arbitrary shell execution, or automatic merge/deploy.
- Do not make LangSmith the transactional source of truth or use an LLM judge as a replacement for deterministic checks.
- Do not claim `verified` when evidence, tests, approval, token budget, or release-report records are missing.
