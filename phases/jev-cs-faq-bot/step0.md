Status: pending
Name: vertical-faq-support-bot

## Read first

- `PRD.md` §§1–6
- `apps/web/db/index.ts`, `apps/web/db/schema/index.ts`
- `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/package.json`
- `apps/web/tests/`
- JEV API contract: `POST https://api.typesafe.ai/v1/systemone`, server-only Bearer key, `state`, and typed `questions` (`choice`/`noul`/`score`)

## Task

Implement the complete minimal vertical slice for the JEV-routed FAQ Support bot in the existing repository while keeping the backend extraction-ready. The service must be layered as catalog/repository → deterministic matcher → provider port/JEV adapter → policy service → HTTP route, and the browser must use only the HTTP route.

Create a Drizzle-owned FAQ catalog and migration/seed data. Exact or alias matches must return an allowlisted catalog answer without a provider call. Only misses or ambiguous questions may make one bounded JEV call. Send normalized/redacted text plus a small bounded candidate set; never send tenant, account, payment, auth, or conversation history. Parse and validate JEV's typed answer, confidence, category, and FAQ ID. JEV may select a known FAQ only; it must never author the answer. Low confidence, malformed output, timeout, missing key, disabled provider, rate limit, or provider error must return a deterministic clarification/support fallback.

Add a versioned `POST /api/faq` contract and a `GET /api/faq` catalog/preset contract, with request-size validation, a small server-side rate limiter, timeout/circuit behavior, and redacted structured logging. Add a bottom-right client widget to the existing layout with preset questions, free-text input, loading/error states, allowlisted answer rendering, and a visible support CTA. Do not expose JEV credentials or make browser-to-provider requests.

Use no new dependency unless necessary. Add focused tests for schema/catalog validation, exact/alias zero-call behavior, JEV request/response parsing, confidence gates, redaction, fallback/error paths, API validation, and widget contract. Update `.env.example` and concise local/staging instructions. Keep the default local path deterministic and provider-free; JEV becomes active only when the server-side feature flag and key are present.

## Acceptance Criteria

- `faq_entries` is represented in Drizzle with a committed migration and deterministic seed records; repository reads are isolated behind a FAQ repository contract.
- Exact/alias FAQ questions return the catalog answer and make zero JEV calls; unknown/ambiguous questions make at most one bounded provider call and never return provider-generated prose.
- `POST /api/faq` and `GET /api/faq` return a versioned, validated response with `answer`, `clarify`, and `handoff` outcomes; malformed provider output and provider failure fail closed.
- The bottom-right widget is present from the root layout, works with preset questions and typed input, renders only catalog text, and exposes the fixed support CTA on fallback.
- Focused tests, web lint, full web tests, and production build pass without secrets or production database writes; the final output records exact commands, exit codes, and test counts.

## Verification & Status Update

Run the focused FAQ tests first, then `pnpm --filter ai-saas-foundation-web lint`, `pnpm --filter ai-saas-foundation-web test:all`, and `git diff --check`. Use mocked `fetch` for JEV tests and do not require a live JEV key. Record the results in `phases/jev-cs-faq-bot/step0-output.json` and update the phase handoff with any live-provider gate that remains unverified.

## Don't

- Do not add open-ended answer generation, RAG, embeddings, memory, tools, shell access, attachments, ticket creation, account actions, refunds, payment actions, or arbitrary external calls.
- Do not put `JEV_API_KEY`/`TYPESAFE_API_KEY` in client code, database rows, fixtures, logs, or committed env files.
- Do not let JEV choose an arbitrary URL or answer text; map only validated FAQ IDs to catalog-owned content.
- Do not silently use a paid provider in local tests or silently fall back to a production in-memory catalog when a production database is required.
