Status: completed
Name: integration-contracts-and-validators

Task:
Define versioned API contracts for Google OAuth, payment checkout/confirmation/
webhooks, and Agent provider execution. Extend the profile validator so real
integrations are explicit, single-provider, sandbox-safe, bounded, and fail
closed before the server binds.

Acceptance:
- New JSON contracts have examples and pass `foundation.contract_check`.
- Missing or mixed credentials, production mock payment, missing sandbox flag,
  unsupported Agent provider, and missing model key fail validation.
- Secret-bearing values are excluded from `FoundationConfig.values`.
- Deterministic HTTP/provider fixtures exist before live adapters are added.

Verification:
```bash
python3 -m foundation.contract_check
python3 -m unittest tests/test_foundation.py tests/test_integration_contracts.py
```
