# Ralph ship confirmation
1. Scope: real Google OAuth, sandbox payment adapters, Agent providers, and web setup guides.
2. Default mode remains local-mock/local provider with no cloud credentials.
3. Provider secrets stay server-side and are excluded from tracked config values.
4. Payment selection is one adapter per environment with sandbox-first validation.
5. Markdown guides are imported from apps/web/content/guides/*.md at build time.
6. The dedicated /guides route renders imported source in a read-only line-numbered editor.
7. Phase steps 7–14 have completed documents and JSON evidence outputs.
8. Contract inventory, 93 Python tests, web lint/build, and verify-local pass.
9. Browser verification passed separate / and /guides routes plus payment and Neon child navigation.
10. PR #7 is at USER_MERGE_REQUIRED; no automatic merge is authorized.
