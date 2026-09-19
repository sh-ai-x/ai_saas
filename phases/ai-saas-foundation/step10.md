Status: completed
Name: agent-provider-runtime

Task:
Add provider-neutral HTTP Agent adapters for OpenAI, Anthropic, and Gemini and
wire the selected adapter into bounded run execution. Preserve local echo as a
deterministic default and keep provider content out of logs and telemetry.

Acceptance:
- Provider/model/key configuration is validated before startup.
- Adapter request/response fixtures cover success, timeout, malformed response,
  rate limit, and usage extraction.
- A real provider run uses the existing reservation/checkpoint/SSE path and
  cannot exceed configured timeout, steps, calls, or output budget.
- No automatic provider escalation or secret leakage occurs.

Verification:
```bash
python3 -m unittest tests/test_agent_provider_runtime.py
```
