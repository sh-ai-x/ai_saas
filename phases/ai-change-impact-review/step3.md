Status: pending
Name: workbench-ui

## Read first

- `PRD.md` §§1–5
- `apps/web/components/foundation-console.tsx`
- `apps/web/components/repository-workspace/`
- `apps/web/app/globals.css`
- `apps/web/tests/`

## Task

Replace the legacy user-facing repository proposal screen with the low-token Change Impact Workbench. Provide local HTML/PDF file selection, local Git directory selection, permission/exclusion preview, review launch/progress, evidence table, affected-module view, risk summary, token budget display, LangSmith link, and ready/revise/blocked decision history. Make clear that the browser never uploads/stores the raw proposal or repository snapshot and that no build/test/code modification is available.

## Acceptance Criteria

- A developer can select a local proposal and repository and see the applied exclusion policy before review.
- Review results clearly show requirement status, source page/section, file/symbol/line evidence, unknowns, risk and cost/token metadata.
- Provider-off deterministic mode is usable and no raw file content is persisted by the browser UI.
- The old repository proposal UI is no longer the primary navigation or landing surface.
- Focused browser tests and web lint pass.

## Verification & Status Update

Run focused component/API contract tests, web lint, and `git diff --check`. Record exact commands and outcomes.

## Don't

- Do not expose provider keys in client code.
- Do not add code execution, build, test, patch, or deploy controls.
- Do not hide exclusion rules or provider/token budget from the user.
