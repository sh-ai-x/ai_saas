# Verification gates

Run gates in this order:

```bash
python3 -m foundation.contract_check
python3 -m unittest tests/test_integration_contracts.py
python3 -m unittest tests/test_google_oauth_provider.py
python3 -m unittest tests/test_payment_sandbox_api.py
python3 -m unittest tests/test_agent_provider_runtime.py
npm --prefix apps/web run lint
npm --prefix apps/web run build
bash scripts/verify-local.sh
```

The provider tests use deterministic HTTP fixtures. They do not send OAuth
codes, payment data, prompts, or API keys to external services. A real sandbox
smoke is a separate operator action after these gates are green.

Record evidence:

```bash
python3 scripts/record-step-outputs.py --step 12
```

The output contains commands, exit codes, duration, and environment notes; it
must not contain secret values.
