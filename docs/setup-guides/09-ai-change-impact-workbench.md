# AI Change Impact Workbench

The workbench is an AI Engineer productivity tool for reviewing a proposal
against the current codebase before implementation. It is not a repository
upload service and not a CI replacement.

## Contract

- Local HTML/PDF/Markdown/text extraction, bounded public document URL fetching, or a local `file://` document selected in the browser produces section/page text and a hash. A proposal document is independent from the selected repository.
- Git-aware analysis includes tracked and unignored files and honors
  `.git/info/exclude` and global excludes.
- Secret, binary, build, symlink, and size policies are independent from
  `.gitignore` and are always applied.
- Deterministic file/symbol/import/evidence analysis happens before any model
  call.
- One LangChain synthesis call and one optional JEV context-filter call are the
  review budget. JEV receives compact evidence candidates and may return
  `selected_evidence_ids` before synthesis; when disabled, the deterministic
  byte budget keeps the context bounded. LangGraph owns stage
  checkpoint/resume/cancel. LangSmith owns redacted trace correlation.
- Review submission is asynchronous: `POST /v1/change-impact/reviews` returns
  `202` with a `review_id`, and the UI polls
  `GET /v1/change-impact/reviews/{review_id}` until `complete` or `failed`.
  This keeps long Ragas evaluations from holding a browser/proxy connection.
- LangGraph runs use a `LangChainTracer` callback configured with the same
  LangSmith project. This creates one parent `proposal.review` trace and
  stage/nested provider runs in the LangSmith console.
- Enable the JEV batch only with server-side `JEV_REVIEW_ENABLED=true`,
  `JEV_API_URL`, and `JEV_API_KEY`; local tests keep it disabled.
- The product never edits the target repository or runs its shell, build, or
  test commands.

## LangSmith environment

Set these variables in `.env.staging` before starting the Neon stack; they are
injected into the `foundation` service by `pnpm docker:neon`:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-server-side-key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=proposal-to-verified-change
LANGSMITH_CONSOLE_URL=https://smith.langchain.com

OPENAI_API_KEY=your-server-side-key
RAGAS_EVALUATOR_MODEL=gpt-4o-mini
RAGAS_EMBEDDING_MODEL=text-embedding-3-small
RAGAS_ANSWER_RELEVANCY_STRICTNESS=3
RAGAS_CACHE_ENABLED=true
```

`LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`/`LANGCHAIN_ENDPOINT` are accepted as
compatibility aliases. The Workbench catalog exposes only tracing status,
project name, and console URL; it never returns the API key. LangSmith receives
the bounded review state and redacted credential-like values, not the complete
repository or ignored files.

## Result vocabulary and proposal delta

- `REQ` means **Requirement**: a functional, quality, or operational requirement the system must provide or preserve.
- `AC` means **Acceptance Criteria**: a concrete, verifiable condition used to decide whether a requirement is complete.
- `implemented` means the bounded evidence covers the requirement.
- `partial` / **Partial implementation** means meaningful code exists, but a material condition, edge case, integration, or acceptance criterion is not evidenced. It is not counted as fully implemented.
- `missing` means no supporting implementation evidence was found; `unknown` means the evidence is insufficient to decide; `contradicted` means the current code conflicts with the requirement.

In the generated proposal view, the color-coded change summary appears above
the unchanged Markdown copy area. It groups **changed**, **deleted**, and
**added** items. Changed items use the form `existing content → revised content`
and include the evidence-based reason. The Copy Markdown action continues to
copy only the generated Markdown proposal.

## Ragas evaluation and evidence quality

The workbench uses official Ragas 0.4.3 collection metrics with OpenAI
evaluation models. Deterministic lexical proxies are not used for the
workbench scores.

- **Faithfulness** checks whether claims in the canonical review explanation
  are supported by the evidence attached to the same REQ/AC.
- **Answer Relevance** checks whether the explanation addresses the requirement;
  strictness `3` uses the default multi-question judge consensus.
- **Context Recall** checks how much of the reference answer is covered by the
  retrieved evidence. An explicit `reference_answer` is preferred; when it is
  absent, the requirement text is used as a clearly-labelled
  `requirement-derived` expected-claims reference, not as observed truth.
- **Evidence Relevance** uses Ragas Context Relevance to judge whether the
  selected evidence is about the requirement.
- **Evidence Integrity** is a cost-free deterministic check for requirement ID,
  path, line range, excerpt, rationale, duplicate pointers, and source hash.
  It validates provenance and freshness; it does not claim that an excerpt is
  the absolute truth of the source file.
- Evidence ranges are intentionally bounded to one to three source lines so
  the deployment contract, UI, and judge all receive the same traceable
  context without turning a large file match into an unbounded prompt.
- The browser workbench applies a separate round-robin interleave only to make
  its preview fair across requirements. The server-side
  `ProposalReviewService._select_relevant_evidence` result is authoritative for
  the submitted review and for Ragas scoring.

The evaluator boundary intentionally exposes seven small Ragas runtime
controls plus the required key, so a Neon/production deployment can tune cost
and reliability without changing code: `RAGAS_EVALUATOR_MODEL`,
`RAGAS_EMBEDDING_MODEL`,
`RAGAS_ANSWER_RELEVANCY_STRICTNESS`, `RAGAS_CACHE_ENABLED`,
`RAGAS_BATCH_SIZE`, `RAGAS_MAX_RETRIES`, and `RAGAS_BATCH_DELAY_SECONDS`, plus
the required `OPENAI_API_KEY`. The first four affect scoring semantics; the
batch/retry/delay controls affect throughput and transient-failure handling.

Scores are averaged over successful REQ/AC samples and show sample counts and
threshold pass counts. Failed Ragas samples do not become zeroes. Exact
input/model/embedding/strictness/source-hash matches use a bounded in-process
cache for reproducibility and cost control; set `RAGAS_CACHE_ENABLED=false`
to force a fresh judge run.

The classification fixture
`docs/proposals/test-classification-coverage.yaml` exercises implemented,
modified, partial, missing, contradicted, and unknown states.

## Portfolio metrics

Record evidence coverage, unknown rate, token/review, p95 review latency,
JEV-human agreement, and the percentage of reviews that identify a missing
safety, cost, or observability requirement. These numbers are more useful in
an AI Engineer portfolio than a generic chatbot demo.
