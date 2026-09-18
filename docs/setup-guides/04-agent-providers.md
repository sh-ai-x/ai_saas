# Agent providers

Start with the deterministic local provider, then configure one bounded real
provider with a server-only API key:

```bash
AGENT_PROVIDER=openai
AGENT_MODEL=gpt-4o-mini
AGENT_API_KEY=runtime-only-secret
AGENT_MAX_OUTPUT_TOKENS=256
AGENT_TIMEOUT_SECONDS=30
```

`POST /v1/agent/execute` reserves credits, checkpoints the model-call key,
calls the selected provider, commits measured usage, and exposes the result via
SSE replay. Prompts, raw provider payloads, and authorization headers are not
logged.

```bash
python3 -m unittest tests/test_agent_provider_runtime.py
```
