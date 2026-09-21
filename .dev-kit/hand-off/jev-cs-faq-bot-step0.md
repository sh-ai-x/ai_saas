# FAQ vertical slice handoff

Implemented catalog/repository → matcher → provider port/OpenAI adapter → policy →
HTTP route, with a root-layout widget that calls only /api/faq. No dependencies
added. Operational instructions: phases/jev-cs-faq-bot/README.md. Verification:
phases/jev-cs-faq-bot/step0-output.json.

Migration 0003 creates faq_entries and deterministic public seed rows, aligned
with the migration already recorded on the Neon `staging` branch. A shell-local
staging migration rerun completed successfully as a no-op; read-only checks
confirmed six stable FAQ IDs and migration hash prefix `c2ec2bdfd4a8`. Local
seed mode is explicit; production without a database fails closed. Existing
pricing integration tests remain gated on their dedicated database configuration.

The local live-provider gate is verified with a synthetic non-personal request
through the OpenAI Responses/Structured Outputs contract. Runtime requires
FAQ_OPENAI_ENABLED=true and a server-injected OPENAI_API_KEY; the key is never
sent to the browser. The provider returns only a typed FAQ selection, while the
application renders catalog-owned English answer prose. No production database
writes occurred in this task; only the shared staging migration was touched.

Operational limits: instance-local rate limiter/circuit, no distributed quota;
apply ingress controls before scaling paid routing. Support CTA is /guides,
the existing troubleshooting destination, not a ticketing or staffed channel.
The widget is covered by SSR presence and mocked HTTP/client-contract tests.
Interactive smoke at http://127.0.0.1:3019 reproduced the initial cold-route
timeout: the FAQ catalog route took about 28 seconds to compile while the
widget used a 15-second timeout. The widget now uses a 60-second catalog-load
timeout and keeps answer requests at 15 seconds; the preset catalog and answer
were rechecked in the browser with no error overlay.

The English catalog is applied by migration 0004. The isolated Docker smoke
stack is running at http://127.0.0.1:3021 with FAQ_OPENAI_ENABLED=true,
OPENAI_MODEL=gpt-4o-mini, and OPENAI_TIMEOUT_MS=5000. A browser test of
"Tell me about AI SaaS Foundation." returned the catalog answer through
Your question; broad or ambiguous questions correctly return the clarify
fallback.
