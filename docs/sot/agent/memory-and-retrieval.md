---
doc_id: agent-memory-retrieval
domain: agent
purpose: Define durable run state, long-term memory, embeddings, and permission-aware retrieval.
read_when:
  - changing checkpoints, memory, embeddings, chunks, or vector search
  - changing document permissions or tenant isolation in RAG
audience:
  - user
  - agent
  - reviewer
  - operator
prerequisites:
  - ../00-index.md
  - ../architecture/system-map.md
  - ../security/safety-boundaries.md
source_of_truth: contract
owner: data-platform
last_reviewed: 2026-09-17
change_impact: high
---

# Memory and Retrieval

## State separation

- **Run state:** LangGraph checkpoints for thread continuity, recovery, and
  human-in-the-loop pauses.
- **Product state:** Postgres records users, plans, entitlements, credits,
  payment events, audit events, and durable run metadata.
- **Long-term memory:** explicit user/tenant-scoped facts or preferences with
  a retention and deletion policy.
- **Retrieval index:** embeddings and chunks linked to a source document and
  its authorization scope.

LangGraph distinguishes thread-scoped checkpoints from cross-thread stores.
**(source: https://langchain-ai.github.io/langgraphjs/how-tos/cross-thread-persistence-functional/)**

## Retrieval contract

1. Resolve authenticated user and tenant scope.
2. Apply authorization filters before similarity ranking.
3. Retrieve only documents the caller can access.
4. Preserve source document IDs and chunk IDs in the agent context and trace.
5. Mark retrieved content as untrusted data, not instructions that can expand
   tool permissions.
6. Enforce retention, deletion, and reindex behavior when source permissions
   change.

Supabase documents permission-aware RAG with Postgres RLS and pgvector. **(source:
https://supabase.com/docs/guides/ai/rag-with-permissions)**

## Data rules

- Do not store raw secrets, payment credentials, or unnecessary PII in memory.
- Every memory item has owner, scope, source, created time, expiry or review
  policy, and deletion behavior.
- Embeddings are not treated as anonymous; they inherit source permissions.
- Schema and embedding model changes require a migration/reindex plan.
- Retrieval failures fail closed for protected content; empty retrieval is
  safer than unauthorized retrieval.

## Verification evidence

- Cross-tenant retrieval tests.
- RLS tests for direct and vector queries.
- Deleted-document tests prove chunks are no longer retrievable.
- Checkpoint resume tests after worker failure and approval interruption.
- Prompt-injection tests in retrieved content.
- Reindex tests preserve document identity and permissions.

## Sources

- [LangGraph persistence](https://langchain-ai.github.io/langgraphjs/how-tos/cross-thread-persistence-functional/)
- [Supabase RAG with permissions](https://supabase.com/docs/guides/ai/rag-with-permissions)
- [Supabase database overview](https://supabase.com/docs/guides/database/overview)
