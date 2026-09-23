# Integration setup guides

These guides are the operator-facing source for enabling real integrations.
The same categories are rendered in the dedicated guide console at
`/guides` on the published web port. The product landing and operator console
remain at `/`.

| Category | Guide | Credential boundary |
|---|---|---|
| Start | [00-local-foundation.md](00-local-foundation.md) | none required; process or Docker mode |
| Auth | [01-google-oauth.md](01-google-oauth.md) | Google client secret: server only |
| Payments / Toss | [02-payment-toss.md](02-payment-toss.md) | Toss test keys: server only |
| Payments / Lemon Squeezy | [03-payment-lemonsqueezy.md](03-payment-lemonsqueezy.md) | test API/signing keys: server only |
| Verify | [05-verification.md](05-verification.md) | deterministic fixtures first |
| AI Engineer review | [09-ai-change-impact-workbench.md](09-ai-change-impact-workbench.md) | local proposal-to-code evidence, low-token budget |
| Operate | [06-operations.md](06-operations.md) | managed secret store in deployment |
| Database / Neon | [07-neon-database.md](07-neon-database.md) | Neon connection values: ignored env only |
| Admin / Pricing | [08-pricing-admin.md](08-pricing-admin.md) | admin token/session server-side; provider secrets runtime-only |

The local profile is intentionally complete without external credentials. Move
to a real integration only after the API contract and fixture tests pass.

For the cross-environment branch, Neon, Docker, Vercel, EC2, migration, and
rollback policy, use the [deployment runbook](../sot/operations/deployment-runbook.md).
