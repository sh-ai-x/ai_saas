# Agent providers

## Provider selection

The run service uses one provider-neutral model port. Start with local echo;
then configure one real provider with a low-cost model and strict bounds.

```bash
AGENT_PROVIDER=openai
AGENT_MODEL=gpt-4o-mini
AGENT_API_KEY=runtime-only-secret
AGENT_MAX_OUTPUT_TOKENS=256
AGENT_TIMEOUT_SECONDS=30
```

Anthropic and Gemini use the same settings with their provider/model values.
`AGENT_BASE_URL` is optional for a compatible test gateway.

## API flow

```text
POST /v1/agent/execute
  -> reserve credits
  -> checkpoint model-call idempotency key
  -> call selected provider
  -> commit measured usage
  -> replay result at /v1/runs/{run_id}/events
```

Provider keys are read only by the server adapter. Prompts, authorization
headers, and raw provider payloads are excluded from logs and telemetry.

## Cost and failure controls

`AGENT_MAX_OUTPUT_TOKENS`, `AGENT_TIMEOUT_SECONDS`, run steps, model calls, and
tenant quota are hard limits. Provider timeouts and rate limits fail the run
with a generic recoverable error; no automatic paid fallback is attempted.

```bash
python3 -m unittest tests/test_agent_provider_runtime.py
```
