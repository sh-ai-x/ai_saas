# FAQ support slice

Local: `pnpm install --frozen-lockfile`, then
`pnpm --filter ai-saas-foundation-web dev`. With no DATABASE_URL and
FAQ_OPENAI_ENABLED=false, the catalog uses validated seed records and never
calls a paid provider. Open FAQ & Support at the bottom right. The fixed
Support guide CTA opens the existing /guides troubleshooting surface; there is
no ticket creation or staffed support channel configured in this repo.

Staging: set APP_ENV=staging and DATABASE_URL to a staging database, review
`apps/web/drizzle/0003_faq_catalog.sql`, then run
`pnpm --filter ai-saas-foundation-web db:migrate` against that staging database.
Production requires APP_ENV=production and DATABASE_URL; missing/failed database
reads fail closed, without switching to local seeds. Do not run migrations
against production as part of tests. Seed records in the migration and local
seed are identical. Drizzle owns the schema and migration snapshot.

The AI router is opt-in: inject OPENAI_API_KEY server-side and set
FAQ_OPENAI_ENABLED=true. Restart the server after changing these settings.
Never use NEXT_PUBLIC keys. The adapter uses OpenAI's
`POST https://api.openai.com/v1/responses` contract with `gpt-4o-mini`,
`store:false`, no tools, and strict `text.format.type=json_schema` output.
The model returns only a FAQ ID, category, answerability, and confidence.
The local Docker smoke stack passes `OPENAI_TIMEOUT_MS=5000` to accommodate
container network latency. Before enabling in staging, verify the account
budget, region/privacy requirements, model availability, and confidence
thresholds on synthetic non-personal questions.

POST /api/faq accepts only `{ "version": "1", "question": "service overview" }`.
The body limit is 2048 bytes and the question limit is 500 characters. Responses
have version, outcome (answer/clarify/handoff), answer (catalog text or null),
and a fixed support link. Answer responses include faqId; fallbacks include a
fixed message. GET returns version, entries, support. GET failures return the
handoff contract. All responses are no-store. Invalid input uses 400/413/415,
rate limits use 429, and unavailable GET catalog uses 503.

The policy matches exact questions/aliases first, blocks sensitive questions
from external routing, then sends normalized/redacted text and at most five
public candidate questions. It does not pass HTTP headers, sessions, history,
answers, or database context to OpenAI. Unknown IDs, invalid schema output,
category mismatches, confidence below .85, or answerability=false fail closed.
OpenAI cannot supply answer prose or links. The client also checks returned
answers against GET catalog entries and renders plain React text.

The per-process limiter permits 60 requests/minute across GET and POST, with no
IP/user storage. The catalog is cached for 30 seconds per process. OpenAI
permits one in-flight request/process, a 5000ms deadline, 16KiB response limit,
no retries or redirects, and a 30-second failure cooldown. These are
instance-local bounds; multiple serverless instances multiply the budget.
Configure an ingress rate limit before scaling a paid deployment. Logs contain
only event, outcome, status; never question, provider body or error.

Verification (mocked provider, no keys or DB writes):

```sh
pnpm --filter ai-saas-foundation-web test --runTestsByPath tests/faq.test.ts
pnpm --filter ai-saas-foundation-web lint
pnpm --filter ai-saas-foundation-web test:all
git diff --check
```

## Jev provider (alternative router)

Jev was this feature's original provider (see
`phases/jev-faq-provider-restore/`) and is available again as a
config-flagged alternative behind the same `FaqProvider` port. Set
`FAQ_PROVIDER=jev` plus `JEV_API_KEY` to switch; leave `FAQ_PROVIDER` unset
or anything other than `jev` to keep the OpenAI router above, which remains
the default. Restart the server after changing either setting. For the
request-flow walkthrough — where Jev is called, what it is asked, and how its
response is validated — see `phases/jev-faq-provider-restore/README.md`.

Every safety, redaction, rate-limit, and fail-closed property documented
above for OpenAI applies identically to Jev — same guard set, same
`confidence >= .85 && answerable >= .9` gate, same 5000ms timeout budget
(`JEV_TIMEOUT_MS`, shared `DEFAULT_PROVIDER_TIMEOUT_MS` constant), same
30-second circuit-breaker cooldown on failure. The one behavioral
difference: Jev's `answerable` is a real Noul probability, where OpenAI's is
a boolean cast to `1|0` — see `phases/jev-faq-provider-restore/README.md`
for why that matters.

Jev is inert by construction without `JEV_API_KEY` — `FAQ_PROVIDER=jev` with
no key degrades to the existing clarify fallback, never an error. No live
Jev traffic has been sent from an automated test or CI; the one live check
performed against the real endpoint was manual, one-time, and outside CI
(see `phases/jev-faq-provider-restore/step1-output.json`). Verify the wire
contract again before relying on Jev in a new environment.
