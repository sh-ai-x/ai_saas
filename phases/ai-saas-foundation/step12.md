Status: completed
Name: integration-e2e-verification

Task:
Run the complete contract, validator, adapter fixture, API, browser, and local
profile gates. Record setup-guide evidence and document which checks require
provider sandbox credentials versus deterministic fixtures.

Acceptance:
- Local mode passes without Docker or cloud credentials.
- Sandbox fixture mode passes Google/payment/Agent API flows without real
  secrets, while configured sandbox smoke commands are documented.
- Browser verification finds no page or console errors and exercises sidebar,
  login setup, Agent setup, and payment setup pages.
- Browser verification confirms that `/` and `/guides` are separate, the
  Markdown source editor renders imported guide files, the payment group has
  Toss and Lemon Squeezy child pages, the database group has a Neon PostgreSQL
  child page, and the active source can be copied.
- Step outputs are valid JSON and contain commands, exit codes, and environment
  notes without secret values.

Verification:
```bash
bash scripts/verify-local.sh
python3 scripts/record-step-outputs.py --step 12
```
