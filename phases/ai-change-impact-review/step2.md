Status: pending
Name: control-api-review-routes

## Read first

- `PRD.md` §§4–5
- `services/control_api/http.py`
- `services/control_api/auth.py`
- `tests/test_foundation.py`

## Task

Expose review catalog/start/detail/decision endpoints. Accept only bounded structured proposal context and repository analysis context; reject shell/build/test commands and raw snapshot import. Add idempotency, budget/status reporting, tenant scope, checkpoint resume/cancel, artifact retrieval, and human decision history. Keep legacy APIs only where existing contracts require compatibility.

## Acceptance Criteria

- A review can be created, resumed, cancelled, inspected, and decided through authenticated routes.
- Duplicate idempotency keys return the same review without repeating provider calls.
- Request validation rejects raw repository upload, arbitrary commands, secret-bearing context, and oversized payloads.
- Response includes requirements, evidence pointers, risks, token/cost budget, trace URL when available, and decision history.
- API tests pass without a live provider or external network.

## Verification & Status Update

Run focused control API tests, existing foundation tests, and `git diff --check`; record exact outcomes.

## Don't

- Do not execute user-provided paths or commands in the control API.
- Do not remove compatibility routes until their tests and replacement UI no longer depend on them.
