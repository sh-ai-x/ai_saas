# FAQ vertical slice handoff

Implemented catalog/repository → matcher → provider port/OpenAI adapter → policy →
HTTP route, with a root-layout widget that calls only /api/faq. No dependencies
added. Operational instructions: phases/jev-cs-faq-bot/README.md. Verification:
phases/jev-cs-faq-bot/step0-output.json.

Migration 0003 creates faq_entries and deterministic public seed rows. Migration
application was not performed against any database. Local seed mode is explicit;
production without a database fails closed. Existing pricing integration tests
remain gated on their dedicated database configuration.

Live-provider gate remains unverified: a staging-only synthetic request must
confirm the deployed OpenAI Responses/Structured Outputs contract and confidence
behavior before rollout. Runtime requires FAQ_OPENAI_ENABLED=true and a
server-injected OPENAI_API_KEY. No live provider requests or production database
writes occurred in this task.

Operational limits: instance-local rate limiter/circuit, no distributed quota;
apply ingress controls before scaling paid routing. Support CTA is /guides,
the existing troubleshooting destination, not a ticketing or staffed channel.
The widget is covered by SSR presence and mocked HTTP/client-contract tests;
interactive smoke was also checked at http://127.0.0.1:3019 with the preset
catalog and catalog answer visible.
