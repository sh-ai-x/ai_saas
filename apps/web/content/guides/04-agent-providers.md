---
id: agent-providers
category: AGENT
title: Real model providers
summary: Route bounded runs through OpenAI, Anthropic, or Gemini without leaking keys.
---
# Real model providers

## 1. Choose a provider

The local echo model is deterministic. A real provider is enabled only when a
runtime API key is present; there is no silent paid fallback.

```bash
AGENT_PROVIDER=openai
AGENT_MODEL=gpt-4o-mini
AGENT_API_KEY=runtime-only-secret
AGENT_MAX_OUTPUT_TOKENS=256
AGENT_TIMEOUT_SECONDS=30
```

Use `anthropic` or `gemini` with the matching model value for those providers.

## 2. Execute through the API

```text
POST /v1/agent/execute
  -> reserve credits
  -> checkpoint model-call idempotency key
  -> call selected provider
  -> commit measured usage
  -> replay result at /v1/runs/{run_id}/events
```

## 3. Control cost

Output, timeout, run-step, model-call, and tenant quota limits are hard stops.
Provider errors fail the run with a generic recoverable message. Prompts,
authorization headers, and raw provider payloads are excluded from telemetry.
