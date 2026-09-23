Status: pending
Name: local-context-contracts

## Read first

- `PRD.md` §§1–5
- `docs/setup-guides/09-ai-change-impact-workbench.md`
- `services/control_api/repository_catalog.py`
- `services/agent_orchestrator/model_port.py`
- `tests/test_local_repository_catalog.py`

## Task

Implement the deterministic local context boundary. Parse HTML and PDF metadata/text locally, create a Git-aware manifest from tracked plus unignored files, apply info/exclude/global-exclude, secret/binary/build/size/symlink policies, and produce code structure plus import/symbol/workflow candidates. Add bounded top-k evidence retrieval without invoking a model. Preserve source section/page and file/symbol/line pointers. Never execute repository code or create a repository snapshot.

## Acceptance Criteria

- HTML/PDF parsing produces bounded sections, page/source pointers, and a content hash without storing the original file.
- Git manifest includes tracked and unignored files and excludes ignored, secret, binary, build, oversized, and symlink-escaping files.
- Code analysis is read-only and returns deterministic symbols/imports/routes/config/workflow candidates; parser failures become `unknown`.
- Evidence retrieval returns at most five snippets per requirement and never calls LangChain/JEV.
- Focused tests cover the exclusion and no-execution contracts.

## Verification & Status Update

Run focused Python tests for the local context package and `git diff --check`. Record exact commands and results in the phase output.

## Don't

- Do not upload or persist raw proposal files or repository snapshots.
- Do not invoke an LLM, JEV, shell command from repository content, build, or test suite.
- Do not weaken existing repository authorization tests.
