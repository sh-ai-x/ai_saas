# FAQ vertical slice handoff

Implemented catalog/repository → matcher → provider port/JEV adapter → policy →
HTTP route, with a root-layout widget that calls only /api/faq. No dependencies
added. Operational instructions: phases/jev-cs-faq-bot/README.md. Verification:
phases/jev-cs-faq-bot/step0-output.json.

Migration 0003 creates faq_entries and deterministic public seed rows. Migration
application was not performed against any database. Local seed mode is explicit;
production without a database fails closed. Existing pricing integration tests
remain gated on their dedicated database configuration.

Live-provider gate remains unverified: a staging-only synthetic request must
confirm the deployed JEV wire contract and confidence behavior before rollout.
Runtime requires FAQ_JEV_ENABLED=true and a server-injected JEV_API_KEY. No live
provider requests or production database writes occurred in this task.

Operational limits: instance-local rate limiter/circuit, no distributed quota;
apply ingress controls before scaling paid routing. Support CTA is /guides,
the existing troubleshooting destination, not a ticketing or staffed channel.
The widget is covered by SSR presence and mocked HTTP/client-contract tests;
interactive browser smoke testing is not part of the recorded Jest evidence.
