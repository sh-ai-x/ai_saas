Status: pending
Name: legacy-cleanup-and-docs

## Read first

- `PRD.md` §3 and §6
- `docs/setup-guides/09-ai-change-impact-workbench.md`
- `apps/web/components/repository-workspace/`
- `apps/web/content/guides/00-local-foundation.md`
- `docs/sot/`

## Task

Remove or quarantine obsolete repository-upload/proposal-verification UI and stale user-facing documentation that conflicts with the Proposal-to-Code Review product. Keep compatibility backend contracts only when tests or external callers still require them, and document their deprecation. Add the low-token setup guide, operational limits, privacy boundary, provider configuration, and portfolio metrics. Do not delete unrelated billing/auth/foundation behavior.

## Acceptance Criteria

- No user-facing guide claims that the product uploads an entire repository or runs implementation verification.
- Obsolete UI imports, dead styles, and stale proposal copy are removed or clearly quarantined with a deprecation note.
- Setup guide documents Git exclusion, secret/size limits, one-call budget, LangGraph/LangChain/LangSmith/JEV roles, and no-code-execution boundary.
- Python focused tests, web lint/tests/build, and diff checks pass or failures are explicitly recorded with cause.

## Verification & Status Update

Run the full proportionate verification suite and record exit codes, test counts, known environment-only failures, and final hand-off details.

## Don't

- Do not remove data migrations or compatibility APIs that are still exercised.
- Do not claim code correctness or test execution from this product.
- Do not commit credentials or raw proposal/repository fixtures.
