---
id: verification
category: VERIFY
title: Verification gates
summary: Run deterministic fixtures before using sandbox credentials.
---
# Verification gates

## 1. Validate configuration

The server rejects missing secrets, mixed payment providers, production mock
payments, non-sandbox staging payments, invalid provider configuration, and
invalid bounds before binding.

```bash
uv run --locked python -m foundation.config --env-file .env --profile free-portfolio
```

## 2. Run provider fixtures

```bash
uv run --locked python -m unittest tests/test_integration_contracts.py tests/test_google_oauth_provider.py tests/test_payment_sandbox_api.py
```

Fixtures prove API semantics without spending money or sending prompts to a
provider.

## 3. Run the full gate

```bash
bash scripts/verify-local.sh
uv run --locked python scripts/record-step-outputs.py --step 12
```

Step output contains commands, exit codes, duration, and environment notes,
never secret values.
