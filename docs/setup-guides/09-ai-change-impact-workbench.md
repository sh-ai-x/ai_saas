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
- LangGraph runs use a `LangChainTracer` callback configured with the same
  LangSmith project. This creates one parent `proposal.review` trace and
  stage/nested provider runs in the LangSmith console.
- Enable the JEV batch only with server-side `JEV_REVIEW_ENABLED=true`,
  `JEV_API_URL`, and `JEV_API_KEY`; local tests keep it disabled.
- The product never edits the target repository or runs its shell, build, or
  test commands.

## LangSmith environment

Set these variables in the repository `.env` before starting the local stack;
they are injected into the `foundation` service by `pnpm docker:local`:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-server-side-key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=proposal-to-verified-change
LANGSMITH_CONSOLE_URL=https://smith.langchain.com
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

## Portfolio metrics

Record evidence coverage, unknown rate, token/review, p95 review latency,
JEV-human agreement, and the percentage of reviews that identify a missing
safety, cost, or observability requirement. These numbers are more useful in
an AI Engineer portfolio than a generic chatbot demo.
