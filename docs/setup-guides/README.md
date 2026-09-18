# Integration setup guides

These guides are the operator-facing source for enabling real integrations.
The same categories are rendered in the left sidebar of the local web console
at `http://127.0.0.1:3000`.

| Category | Guide | Credential boundary |
|---|---|---|
| Start | [00-local-foundation.md](00-local-foundation.md) | none required |
| Auth | [01-google-oauth.md](01-google-oauth.md) | Google client secret: server only |
| Payments | [02-sandbox-payments.md](02-sandbox-payments.md) | one Toss or Lemon Squeezy sandbox |
| Agent | [03-agent-providers.md](03-agent-providers.md) | model API key: server only |
| Verify | [04-verification.md](04-verification.md) | deterministic fixtures first |
| Operate | [05-operations.md](05-operations.md) | managed secret store in deployment |

The local profile is intentionally complete without external credentials. Move
to a real integration only after the API contract and fixture tests pass.
