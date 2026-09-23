# PRD — AI Change Impact Workbench: Low-token Proposal Review

## 1. Frame

- Goal: Build a read-only workbench that compares an HTML/PDF/Markdown/text proposal from a local file, public URL, mounted-worktree `file://` URL, or direct text input with a local Git repository and returns requirement-level code evidence, impact, risks, and a human-reviewed ready/revise/blocked decision.
- Target user: An AI Engineer evaluating prompt, model, retriever, graph, or provider changes before implementation.
- Situation: The engineer currently has to read the proposal, search the repository, infer affected modules, and judge feasibility manually; LLM/JEV calls over the entire repository are expensive and hard to reproduce.

## 2. Validate

### Independent evidence

1. **Repository evidence:** `services/control_api/repository_catalog.py:400-468` currently imports repository snapshots, which creates size, secret, and storage concerns for large local repositories.
2. **Runtime evidence:** `services/agent_orchestrator/model_port.py:57-166`, `services/agent_orchestrator/langgraph_runtime.py:37-123`, and `services/observability/adapter.py:67-161` provide partial LangChain/LangGraph/LangSmith seams but no proposal-to-code evidence review artifact.
3. **Interview PDF:** BASWE 100 AI Engineering Interview Questions, Q41-Q60 and Q61-Q80, requires traceability, versioned artifacts, cost/latency measurement, failure-first analysis, and safety gates.
4. **Projects PDF:** BASWE Build These Six Projects, Project 4 and Project 6, requires calibrated evaluation, human review, severity, reproduction, and needs-review findings.

### Value score

Assumption: 240 value units per first-year engineer, 25 reachable early users, and 1,200 cost units for a bounded vertical slice.

`value_score = (240 × 25) / 1,200 = 5.0` — PASS (threshold ≥ 3.0).

### Ambiguity loop

`ambiguity_score: 10 → 8 → 6 → 4 → 3` — PASS.

- The first loop fixed the product to proposal-to-code review instead of repository upload or code execution.
- The second fixed local parsing and Git-standard exclusion.
- The third fixed deterministic analysis before model calls.
- The fourth fixed one LangChain synthesis call and optional one JEV batch call per review.
- The final loop fixed the MVP boundary: no code modification, shell, build, test suite, or deployment.

## 3. Non-goals

1. **Full repository upload or snapshot storage.** Rationale: it increases cost and secret exposure. Breach response: create a separate ingestion/security plan.
2. **Code modification, shell execution, build, test suite, or deployment.** Rationale: proposal review must remain separate from implementation verification. Breach response: hand the artifact to CI or a separate implementation phase.
3. **File-by-file LLM or JEV evaluation.** Rationale: deterministic manifest/AST/search is cheaper and more reproducible. Breach response: add a separately budgeted targeted evaluator only for unresolved evidence.
4. **Baseline/candidate bulk experiment execution in the MVP.** Rationale: the review must first identify the workflow and metrics worth comparing. Breach response: start the follow-up experiment phase from the approved artifact.

## 4. Phase plan

Phase index: `phases/ai-change-impact-review/index.json`

### Step 0 — local-context-contracts

Implement bounded local HTML/PDF/Markdown/text, public document URL, mounted-worktree `file://`, or direct text metadata extraction, Git-aware manifest, secret/size/symlink policy, deterministic code structure analyzer, and bounded evidence retrieval.

### Step 1 — review-graph-and-evaluation

Implement LangGraph checkpoint flow, LangChain single-call structured synthesis, optional single-call JEV adapter, redacted LangSmith review trace, and immutable review artifact.

### Step 2 — control-api-review-routes

Expose catalog/start/detail/decision endpoints with idempotency, budget reporting, no-code-execution validation, and review state persistence.

### Step 3 — workbench-ui

Replace the legacy repository proposal UI with local document/repository selection, exclusion preview, review progress, evidence table, risk summary, and human decision UI.

### Step 4 — legacy-cleanup-and-docs

Remove obsolete repository-import/proposal UI paths and stale documentation from the user-facing workflow, keep only compatibility APIs required by existing tests, add setup guide, and run focused/full verification.

## 5. Acceptance criteria

1. Local HTML/PDF/Markdown/text files, public document URLs, direct text, or `file://` URLs inside the mounted worktree and Git repositories are analyzed without raw source or repository snapshot storage; remote documents are limited to 10 seconds and 12 MB.
2. Git tracked + unignored files are included; secret, binary, build, size, and symlink policies are enforced.
3. Requirements and acceptance criteria retain source section/page pointers and map to top-k file/symbol/line evidence.
4. Review uses at most one LangChain synthesis call and one optional JEV call, while LangGraph supports checkpoint/resume/cancel and LangSmith links review metadata and cost.
5. UI shows supported/partial/missing/contradicted/unknown, affected modules, safety/cost/latency/observability gaps, and human ready/revise/blocked history; no code/build/test/deploy action is available.

## 6. Hand-off

- Product guide: `docs/setup-guides/09-ai-change-impact-workbench.md`
- Phase: `phases/ai-change-impact-review/index.json`
- Next stage: `/dev-kit:build`
- Build order is dependency-first and remains in the current `fix/local-repository-picker` worktree; main is not edited.
