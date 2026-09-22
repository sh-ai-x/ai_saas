# Implementation Status — Proposal-to-Verified-Change Agent

> Companion to [`docs/proposals/applied/proposal-to-verified-change-agent/idea-proposal-to-verified-change-agent.yaml`](./idea-proposal-to-verified-change-agent.yaml). Lists what the Local Lite + offline slice actually delivers vs. what is intentionally deferred.
>
> Snapshot of `feat/proposal-to-verified-change-agent @ e28745f`.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Wired + tested |
| 🟡 | Wired but stub / partial |
| ⏳ | Not implemented (deferred to a later phase) |
| 🚫 | Explicit out-of-scope (see rule R1–R14) |

## Kernel — `agent_platform/` (700 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `contracts.py` | 187 | ✅ | `Requirement`, `EvidenceReference`, `Plan`, `ApprovalToken`, `RunLifecycle`, `ReleaseReport`, `UsageRecord`, `PackRejectionError` |
| `ports.py` | 44 | ✅ | `ProjectPackPort`, `StructuredModelPort`, `TracePort`, `SandboxPort`, `DeliveryPort` Protocols — kernel imports ports only |
| `budgets.py` | 137 | ✅ | `TokenBudgetLedger`, `BudgetPolicy.local_lite`, `BudgetPhase` (analyze/plan/verify), reserve/refund/reconcile |
| `cache.py` | 36 | ✅ | `ContentAddressedContextCache` — deterministic dedupe, hit/miss, `retrieval_expansion` counter |
| `redaction.py` | 37 | ✅ | Server-side redact for telemetry and audit payload |
| `storage.py` | 269 | ✅ | SQLite `KernelStore` — run lifecycle, checkpoint, approval issue/consume, usage, event ledger, report |

Verification: `uv run --locked python -m pytest -q tests/test_proposal_verified_change_agent.py tests/test_runtime_boundaries.py` → 13 passed.

## Project Pack — `project_packs/proposal_to_verified_change/` (180 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `pack.py` | 104 | ✅ | `ProposalToVerifiedChangePack.parse_proposal / evidence / build_plan`. Deterministic parser + repository evidence |
| `index.py` | 70 | ✅ | `RepositoryIndex` — path allowlist (`agent_platform/`, `services/`, `project_packs/`, `tests/`), SHA-256 line hash, symbol extraction |

Wired into kernel via `ProjectPackPort`. Replaceable per rule R9 (kernel imports ports only).

## Agent Orchestrator — `services/agent_orchestrator/` (547 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `workflow.py` | 268 | ✅ | `ProposalVerifiedWorkflow.run` — full graph (intake → profile_validate → inventory → retrieve → analyze → plan → human_approval → patch → test → evaluate → report). Approval interrupt, budget fail-closed, deterministic evaluator |
| `graph.py` | 39 | ✅ | `NODE_NAMES` + lightweight graph definition (intake / profile_validate / inventory / retrieve / analyze / plan / human_approval / patch / test / evaluate / report) |
| `langgraph_runtime.py` | 76 | ✅ | `LangGraphRuntime.checkpoint` — optional LangGraph adapter; off by default in Local Lite |
| `model_port.py` | 164 | ✅ | `FakeStructuredModel` (default), `StructuredModelPort` Protocol, `PromptContextAdapter` for redacted prompt building |

## Control API — `services/control_api/` (381 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `__main__.py` | 11 | ✅ | Entry: `python3 -m services.control_api` |
| `service.py` | 16 | ✅ | Wiring: store + pack + workflow + adapters |
| `http.py` | 268 | ✅ | Authenticated HTTP/SSE control API: `POST /v1/runs`, `GET /v1/runs/{id}`, approval interrupt endpoint, `/healthz`, SSE replay |
| `auth.py` | 86 | ✅ | Tenant-scoped bearer auth (`x-tenant-id-local-or-signed-bearer` per Local Lite profile) |

## Sandbox Worker — `services/sandbox_worker/` (148 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `sandbox.py` | 148 | ✅ | `DeterministicSandbox` — allowlisted fixture commands, retry-once policy, no arbitrary shell, no network egress. Replaces real container in Local Lite |

Production isolation boundary is **out of scope** for this PR (PR #32 tracks the title-scoped Docker/Neon isolation); Local Lite is bounded but not the production isolation target (rule R7/R12).

## Delivery Gateway — `services/delivery_gateway/` (90 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `gateway.py` | 42 | ✅ | `DeliveryPort.sign / validate` — only operates on a verified package + scoped policy decision; no ambient credentials |
| `artifact.py` | 48 | ✅ | Atomic, redacted review-artifact persistence |

Real Git/CI provider adapters (GitHub Actions, GitLab, Buildkite) are **deferred** (⏳) — they require per-provider conformance packs before they can claim verified delivery.

## Observability — `services/observability/` (234 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `otel.py` | 172 | ✅ | OTel exporter + memory span sink for Local Lite |
| `adapter.py` | 62 | ✅ | Redacted LangSmith telemetry seam — off by default; never the product authority |

## Evaluation — `services/evaluation/` (82 LOC)

| Module | LOC | Status | Notes |
|---|---:|---|---|
| `metrics.py` | 42 | ✅ | Coverage / evidence-precision / unsupported-claim / latency / token / cost / safety metric helpers |
| `report.py` | 40 | ✅ | Deterministic `ReleaseReport` shape with denominator + sample metadata |

## Local Lite profile — `infra/profiles/local-lite/profile.yaml`

- 2 long-lived processes (`control-api` + nginx)
- `provider_mode: fake`
- `state_store: sqlite`
- `network: disabled` for sandbox
- `sandbox_mode: deterministic`
- Token limits: 20,000 plan / 41,000 verify / 8,000 per-call / 5 primary + 1 retry

`infra/nginx/local-lite.conf` exposes port 8080 and proxies `/v1/*` and `/healthz` to `127.0.0.1:8000` with `proxy_buffering off` for SSE.

## What is intentionally NOT in this PR

- 🚫 Real provider bridges in default path — LangChain/LangGraph/LangSmith adapters are wired but **off** (Local Lite uses fake provider)
- 🚫 Production MSA isolation — title-scoped Docker/Neon isolation lives at PR #32, not here
- 🚫 Real Git/CI delivery adapters — only the contract + deterministic placeholder is shipped
- 🚫 8GB peak-RSS enforcement harness — local acceptance gate is documented but not yet enforced by an automated test
- 🚫 Wilson / bootstrap 95% CI computation — metric contract stores raw counts; CI math is the next phase

## Verification (today)

```bash
uv run --locked python -m pytest -q tests/test_proposal_verified_change_agent.py tests/test_runtime_boundaries.py
uv run --locked python -m compileall -q agent_platform services project_packs
uv run --locked python -m pytest -q   # full parent suite, 146 passed
```

Kernel import-boundary check passes (no project-specific imports inside `agent_platform/`).
Applied proposal HTML safety check passes (no `<script>`, no remote fetches).