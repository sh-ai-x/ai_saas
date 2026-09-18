---
doc_id: security-safety-boundaries
domain: security
purpose: Define identity, data, tool, prompt, and operational safety boundaries.
read_when:
  - adding tools, data sources, permissions, secrets, or autonomous actions
  - investigating prompt injection, data leakage, abuse, or runaway cost
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
  - ../auth/google-oauth.md
  - ../agent/runtime-and-tools.md
  - ../agent/memory-and-retrieval.md
source_of_truth: contract
owner: security-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Safety Boundaries

## Control principles

The agent is not trusted with ambient authority. Human control, alignment with
user expectations, secure interactions, transparency, and privacy are required
design principles. **(source: https://www.anthropic.com/research/trustworthy-agents)**

## Identity and authorization

- Authenticate every user and operator request.
- Resolve tenant/resource scope server-side.
- Check entitlement before paid or quota-consuming work.
- Check tool scope before each tool call, not only at session start.
- Separate admin authorization from ordinary user authorization.
- Use least-privilege service credentials and short-lived access where possible.

## Tool safety

Classify tools as read-only, reversible side effect, irreversible side effect,
financial, permission-changing, or external communication. Require explicit
approval for high-impact classes. Validate input and output schemas, enforce
timeouts and budgets, and use idempotency for retries.

## Prompt and retrieval safety

- Treat user content and retrieved documents as untrusted data.
- Never allow retrieved text to change system policy, tool permissions, or
  secret access.
- Detect and log prompt-injection indicators without leaking the payload.
- Restrict outbound destinations and data fields for external actions.
- Apply RLS before vector similarity results are provided to the model.

## Cost and availability safety

- Enforce request, run, user, tenant, provider, step, token, time, and cost
  limits.
- Stop loops after the configured step budget.
- Use bounded retries, circuit breakers, and approved fallbacks.
- Apply queue backpressure and concurrency limits.
- Fail closed for authorization, payment, and protected-data uncertainty.

## Incident containment

Operators must be able to disable a tool, provider, model, route, or user
without deleting evidence. Emergency actions require an audit event and a
recovery/re-enable procedure.

## Verification evidence

- Tool authorization and tenant-isolation tests.
- Prompt-injection and exfiltration scenario tests.
- Secret and PII redaction tests.
- Runaway loop and budget exhaustion tests.
- High-impact approval and emergency disable tests.

## Sources

- [Anthropic: Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [Supabase RAG with permissions](https://supabase.com/docs/guides/ai/rag-with-permissions)
- [LangGraph human-in-the-loop](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/review-tool-calls/)
