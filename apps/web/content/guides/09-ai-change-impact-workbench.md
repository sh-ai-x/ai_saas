---
id: ai-change-impact-workbench
category: AI ENGINEER
title: Proposal-to-code review
summary: Read an HTML/PDF/Markdown/text proposal from a local file, URL, or text input and a Git repository, then review implementation evidence with a strict low-token budget.
---
# Proposal-to-code review

The Change Impact Workbench provides two bounded questions before implementation:

1. **Proposal → Implementation** — how much of each proposal requirement is already represented in the current code.
2. **Proposal → Code impact** — which code boundaries, AI workflow components, and risks a change would affect.

Requirement labels are explicit in every result:

- `REQ` (**Requirement**) means a functional, quality, or operational requirement the system must provide or preserve.
- `AC` (**Acceptance Criteria**) means a concrete, verifiable condition used to decide whether that requirement is complete.

Clicking a `REQ` or `AC` row filters the evidence panel to that item, so its
description, status, rationale, and code range can be reviewed together.

It is a read-only review tool. It does not edit code, execute shell commands,
run a build or test suite, or deploy anything.

## How local input works

1. Select an HTML/PDF/Markdown/text proposal file, paste a public document URL / mounted-worktree `file://` URL, or enter Markdown/plain text directly. Files are parsed locally; URLs are fetched by the bounded Foundation endpoint. All paths produce sections, acceptance criteria, and a hash without storing the original.
2. Select the repository directory. The browser applies `.gitignore`-compatible excludes and the server-side CLI path applies Git `--exclude-standard` semantics, including `.git/info/exclude` and global excludes.
3. Secrets, private keys, binary files, build output, `node_modules`, symlinks, and files above the size cap are excluded.
4. The review sends only bounded requirements, file metadata, symbols/imports, and top-k evidence snippets. The raw proposal and repository snapshot are not stored.

## Low-token policy

- HTML/PDF parsing, Git manifest creation, AST/symbol/import analysis, and evidence retrieval use zero model tokens.
- Remote HTML is limited to `http(s)`, public hosts, a 10-second timeout, and 12 MB; credentials, private hosts, and non-HTML responses are rejected.
- LangChain Structured synthesis is limited to one call per review.
- JEV is optional and limited to one batch call per review.
- LangGraph checkpoints each stage so a review can resume without repeating completed work.
- LangSmith receives the `proposal.review` LangGraph run and its bounded stage runs. Inputs are passed through the platform redactor before export; the workbench never sends the complete repository, secrets, or ignored files.

## LangSmith observability

The Foundation service owns the LangGraph execution, so LangSmith configuration
must be present in the server/container environment, not only in the browser:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-server-side-key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=proposal-to-verified-change
LANGSMITH_CONSOLE_URL=https://smith.langchain.com
```

After `pnpm docker:local`, the Workbench header shows the configured project
and an **Open LangSmith** link. Each review is traced as `proposal.review` with
`prepare`, `jev`, `synthesize`, and `finalize` stages, plus nested LangChain
provider calls. The API key stays server-side; the browser receives only
enabled/project/console status.

## Reading the result

In **Proposal → Implementation**, each requirement is marked `implemented`,
`partial` (partial implementation), `missing`, `contradicted`, or `unknown`. `partial` means
some meaningful code exists, but a material condition, edge case, integration, or
acceptance criterion is not evidenced; it is not counted as fully implemented.
The progress percentage gives full credit to implemented requirements and half
credit to partial requirements; it is evidence-supported coverage, not a test or
deployment result.

In **Proposal → Code impact**, the result first shows a color-coded change summary
with changed, deleted, and added items. A changed item is rendered as
`before → after` with the evidence-based reason. The generated Markdown proposal
and its Copy Markdown action remain unchanged below that summary. The result also shows a generated Markdown proposal,
bounded multi-line code pointers, and a sentence explaining why each range was
selected. Review the safety, cost, latency, observability, and provider gaps
before using the proposal for a later change. The recommendation is evidence,
not an automatic release.

Baseline/candidate execution is intentionally a later phase. First use this
review to select the workflow and metrics worth comparing; then use the
dedicated experiment loop without mixing implementation verification into it.
