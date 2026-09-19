# Integration setup guides

These guides are the operator-facing source for enabling real integrations.
The same categories are rendered in the dedicated guide console at
`http://127.0.0.1:3000/guides`. The product landing and operator console remain
at `/`.

| Category | Guide | Credential boundary |
|---|---|---|
| Start | [00-local-foundation.md](00-local-foundation.md) | none required |
| Auth | [01-google-oauth.md](01-google-oauth.md) | Google client secret: server only |
| Payments / Toss | [02-payment-toss.md](02-payment-toss.md) | Toss test keys: server only |
| Payments / Lemon Squeezy | [03-payment-lemonsqueezy.md](03-payment-lemonsqueezy.md) | test API/signing keys: server only |
| Agent | [04-agent-providers.md](04-agent-providers.md) | model API key: server only |
| Verify | [05-verification.md](05-verification.md) | deterministic fixtures first |
| Operate | [06-operations.md](06-operations.md) | managed secret store in deployment |
| Database / Neon | [07-neon-database.md](07-neon-database.md) | Neon connection values: ignored env only |

The local profile is intentionally complete without external credentials. Move
to a real integration only after the API contract and fixture tests pass.
