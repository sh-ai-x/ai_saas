---
doc_id: verification-release-incident
domain: verification
purpose: Define evidence gates, release checks, incident response, and replay.
read_when:
  - deciding whether a task or release is complete
  - responding to a production failure or replaying an external event
audience:
  - user
  - agent
  - operator
  - reviewer
prerequisites:
  - ../00-index.md
  - ../evidence/evidence-ledger.md
  - ../security/safety-boundaries.md
source_of_truth: contract
owner: quality-and-reliability
last_reviewed: 2026-09-17
change_impact: high
---

# Verification, Release, and Incident Response

## Evidence gate

An agent task is not complete until it provides:

- the acceptance criteria it used
- changed files or documents
- deterministic check results
- relevant traces or evaluation results
- known limitations and unresolved risks
- rollback or follow-up information when applicable

## Verification layers

1. **Static:** formatting, lint, type checks, dependency and secret scans.
2. **Unit:** state transitions, validation, idempotency, authorization, and
   pure business rules.
3. **Contract:** provider payload mapping, webhook signatures, API schemas,
   tool schemas, and document metadata.
4. **Integration:** database transactions, checkpoints, queues, Langfuse,
   gateway, and provider sandboxes.
5. **Scenario/evaluation:** representative agent tasks, safety cases, quality
   datasets, and high-risk human approval paths.
6. **Load/reliability:** concurrency, queue backpressure, timeout, worker
   restart, provider outage, and ECS scaling.
7. **Security:** auth bypass, tenant isolation, prompt injection, exfiltration,
   secret exposure, and admin abuse.

## Release gate

Do not release when a required check is missing, an accepted decision has no
source, a high-impact tool lacks approval, a payment event cannot be replayed,
or the rollback owner and evidence path are unknown.

## Incident flow

```text
detect -> classify -> contain -> preserve evidence -> recover/replay
       -> validate user impact -> communicate -> root cause -> update SOT
```

Containment may disable a route, model, tool, provider, or admin capability.
Recovery must prefer replayable durable events over manual database edits.

## Verification evidence

- Test output and environment are recorded with the change.
- Payment sandbox events can be replayed safely.
- Agent runs can be inspected by `run_id` and trace correlation.
- Incidents record impact, timeline, containment, recovery, root cause, and
  which SOT document changed afterward.

## Sources

- [Anthropic: Effective Harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Harness Design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Langfuse evaluation concepts](https://langfuse.com/docs/evaluation/core-concepts)
- [Toss Payments webhooks](https://docs.tosspayments.com/en/webhooks)
- [Lemon Squeezy webhooks](https://docs.lemonsqueezy.com/help/webhooks)
