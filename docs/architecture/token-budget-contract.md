---
doc_id: token-budget-contract
domain: architecture
purpose: Define bounded, measurable token usage without reducing verification quality.
source_of_truth: contract
owner: platform-engineering
last_reviewed: 2026-09-21
change_impact: high
---

# Token Budget Contract

## Principle

Token optimization is a kernel concern. A Project Pack may define prompt
content and retrieval hints, but it cannot raise a tenant, run, node, or
profile budget. Any optimization that lowers requirement coverage, evidence
precision, safety, or test verification fails the release gate.

## Budget authority

`TokenBudgetPort` owns:

- per-tenant and per-run input/output token limits;
- per-node model-call count, timeout, and retry limits;
- context byte/token limits and retrieved-item limits;
- provider-reported usage and cost reconciliation;
- hard-stop behavior when a budget is exhausted;
- a machine-readable `quota_paused` or `budget_exceeded` result.

Budgets are selected by runtime profile, repository profile, workflow stage, and
tenant plan. The model cannot request a larger budget. A Project Pack can ask
for a lower budget or a different prompt template through a versioned policy.

## Local Lite initial budget

The following is the initial small-repository profile, not a universal model
limit. Values are release-configured and must be measured against quality gates.

| Stage | Max model calls | Input tokens | Output tokens | Default behavior |
| --- | ---: | ---: | ---: | --- |
| requirement parse | 1 | 1,500 | 500 | typed requirements only |
| repository analysis | 1 | 7,000 | 2,000 | targeted evidence, no full repository |
| plan | 1 | 7,000 | 2,000 | structured plan and citations |
| patch proposal | 1 + 1 bounded retry | primary `8,000` / retry `2,000` | primary `4,000` / retry `2,000` | unified diff, no arbitrary file write |
| semantic evaluation | 1 sampled call | 4,000 | 1,000 | deterministic checks run first |
| report | 0 by default | 0 | 0 | rendered from persisted records |

Initial aggregate ceilings:

- plan-only run: `20,000` model tokens (`2,000 + 9,000 + 9,000`);
- verify run: `41,000` model tokens maximum (`20,000` plan stages + `16,000`
  patch stage including its bounded retry + `5,000` semantic evaluation);
- delivery request: `0` additional model tokens by default;
- maximum five primary model calls plus one bounded patch retry;
- context sent to one model call: `<= 8,000` input tokens in Local Lite.

If a run reaches a ceiling, it returns the best evidence-backed partial result
with `quota_paused` or `needs_review`; it never silently truncates evidence or
claims `verified`.

## Context reduction pipeline

Every model call follows this order:

1. Parse the proposal and index the repository without an LLM.
2. Select authorized files/symbols/tests using path, symbol, hash, and
   requirement links.
3. Apply a deterministic byte/token limit and preserve source line ranges.
4. Reuse a content-addressed summary when the repository snapshot and prompt
   version have not changed.
5. Ask the model only for the missing structured decision.
6. Expand retrieval once only when evidence coverage or schema validation
   fails; record the reason and additional token cost.

The system never puts the full repository in a prompt by default. A context
cache key is:

```text
(repo_snapshot, requirement_id, retrieved_hashes, prompt_version,
 model_version, policy_version)
```

Patch proposals and approval decisions are not reused across changed snapshots
or changed policies. Cached read-only analysis must retain its source hashes and
authorization scope.

## Retry and compression rules

- Deterministic schema/path/test failures consume no additional model call.
- A retry receives the failure code, missing evidence IDs, and a compact
  repair context, not the entire previous transcript.
- Summaries are created from source hashes and line ranges; the model cannot
  invent a summary that becomes an authority source.
- Semantic evaluation is sampled after deterministic gates; it is never used
  to compensate for missing tests or evidence.
- Cache hits, compression, expansion, and budget pauses are visible in the
  trace and evaluation ledger.

## Quality guard

An optimization variant is accepted only when it meets the same or better
release gates for requirement coverage, evidence precision, unsupported claims,
critical safety cases, and required test pass status. A lower token count with a
quality regression is a failure, not an optimization.

## Project pivot rule

The token budget manager, context cache, retrieval protocol, and usage ledger
remain in the Agent Platform Kernel. A Project Pack supplies only its prompt
templates, retrieval ranking hints, structured extensions, and dataset. This
allows a future project to use a different context strategy without changing
metering, hard stops, redaction, or release metrics.
