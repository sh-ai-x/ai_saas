# Step 13 — Neon production database

## Objective

Connect the foundation to the authenticated Neon `ai_saas` project without
committing credentials, preserve the free local profile, and expose the setup
as a Markdown guide in the existing `/guides` documentation console.

## Plan

1. Authenticate the Neon CLI in a supported browser profile.
2. Install Neon skills and MCP tooling on the trusted developer machine.
3. Link the `production` branch and pull ignored connection variables.
4. Keep `neon.ts` as an explicit, minimal repository policy and deploy it.
5. Verify the branch with a read-only SQL query and record the result.
6. Import the same setup instructions into the web guide and mirror docs.
7. Run contract, local smoke, web lint/build, and browser navigation checks.

## Acceptance criteria

- The linked cloud project and branch are visible through `neon status`.
- `neon deploy` and `neon config plan` finish without drift.
- A read-only query returns the expected Neon database and PostgreSQL version.
- `.neon` and `.env.local` are ignored and no secret is staged.
- `/guides` shows `DATABASE > Neon PostgreSQL` as a child navigation item.
- The local profile remains runnable without Neon credentials.
