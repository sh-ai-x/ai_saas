Status: completed
Name: identity-tenant-admin

Read first:
- `PRD.md`
- `docs/sot/auth/google-oauth.md`
- `docs/sot/admin/operations-and-audit.md`
- `docs/sot/security/safety-boundaries.md`
- `phases/ai-saas-foundation/step0.md`

Task:
Implement the identity and privileged-operation boundary using Better Auth-compatible session semantics. Add Google OAuth callback validation, tenant/member/RBAC contracts, protected route checks, admin user/plan/credit operations, reason-required mutations, before/after audit events, and cross-tenant denial tests. Keep the first deployment modular while preserving extraction-ready ownership.

Acceptance:
- REQ-2: Google, tenant, admin, and audit contracts are executable and deny unauthorized or cross-tenant operations.

Verification:
uv run --locked python -m lib.intent_integrity --pre ai-saas-foundation

Don't:
- Do not trust email alone as admin authorization.
- Do not expose OAuth secrets or codes to browser, logs, traces, or agent context.
- Do not mutate billing tables directly from the UI.
