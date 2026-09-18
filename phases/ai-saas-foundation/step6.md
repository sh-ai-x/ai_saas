Status: completed
Name: web-console-local-vertical-slice

Read first:
- `PRD.md`
- `docs/service-catalog.md`
- `phases/ai-saas-foundation/step3.md`
- `phases/ai-saas-foundation/step5.md`
- `apps/web/README.md`

Task:
Add the smallest usable web console for the local foundation runtime. The web
surface must remain a thin Next.js App Router client and same-origin proxy; it
must not duplicate tenant, auth, billing, admin, metering, or run state. The
console should make the contract-first vertical slice demonstrable in a
browser without Vercel, Neon, Docker, or provider credentials.

Acceptance:
- `apps/web` builds with Next.js 15 and has no high-severity production npm
  audit findings.
- The console renders health, tenant, balance, run, admin, billing, and
  activity views from the local API.
- Google mock login establishes a session through the API contract.
- A bounded run displays replayed SSE frames and refreshes the shared balance.
- Admin plan/credit mutation and mock payment completion are visible in the
  browser and recorded in the operator trail.
- POST request bodies pass through the App Router proxy intact.
- No cloud account, paid tier, provider SDK, or browser-owned authorization
  state is required for the local profile.

Verification:
```bash
npm --prefix apps/web audit --omit=dev --audit-level=high
npm --prefix apps/web run build
python3 scripts/record-step-outputs.py --step 6
```

Browser evidence:
- `http://127.0.0.1:3000` renders the console.
- Agent-browser found no page errors or console errors beyond the standard
  React DevTools informational message.
- The Google mock login, run/SSE replay, admin mutation, and mock payment
  flows all completed successfully.

Do not:
- Do not put database, payment, tenant, or secret logic in the browser.
- Do not add a production payment provider to the local profile.
- Do not require Vercel, Neon, Cloudflare, AWS, or Docker for this step.
