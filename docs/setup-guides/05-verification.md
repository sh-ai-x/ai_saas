# Verification gates

Run deterministic checks before any sandbox credential:

```bash
python3 -m foundation.contract_check
python3 -m unittest tests/test_integration_contracts.py tests/test_google_oauth_provider.py tests/test_payment_sandbox_api.py
npm --prefix apps/web run lint
npm --prefix apps/web run build
bash scripts/verify-local.sh
python3 scripts/record-step-outputs.py --step 12
```

Fixtures do not send OAuth codes, payment data, prompts, or API keys to
external services. Outputs record exit codes and environment notes only.
