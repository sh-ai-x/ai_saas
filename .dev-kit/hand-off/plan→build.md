# plan → build hand-off

## Plan

- Phase: `ai-change-impact-review`
- Branch/worktree: `fix/local-repository-picker`
- Proposal: `docs/proposals/reviewing/local-document-workspace/docs-first-analysis.html`
- Goal: provide a low-token, read-only proposal-to-code review for an AI Engineer using local HTML/PDF parsing, Git-aware deterministic analysis, one bounded LangChain synthesis call, optional one-call JEV evaluation, LangGraph checkpointing, and LangSmith trace correlation.

## Build order

1. `step0`: local document/Git context, code structure, and bounded evidence contracts.
2. `step1`: LangGraph review graph, LangChain synthesis, optional JEV, LangSmith trace, and artifact store.
3. `step2`: authenticated control API routes with idempotency and no-code-execution validation.
4. `step3`: low-token Change Impact Workbench UI replacing the legacy repository proposal surface.
5. `step4`: legacy cleanup, setup documentation, and proportionate verification.

## Required verification

- No raw proposal file or repository snapshot is uploaded or persisted.
- Git tracked + unignored rules, secret denylist, binary/build/size/symlink limits are visible and tested.
- Deterministic analysis uses zero model tokens; LangChain synthesis is at most one call and JEV at most one optional call per review.
- LangGraph checkpoint/resume/cancel and idempotency are tested.
- LangSmith receives redacted review metadata, not raw repository/document payloads.
- The product does not modify code or run shell/build/test/deploy actions.
