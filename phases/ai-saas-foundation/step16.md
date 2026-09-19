Status: pending
Name: public-app-admin-surfaces

## Read first

- `PRD.md` §8 and REQ-14–REQ-18
- `docs/sot/admin/operations-and-audit.md`
- `docs/sot/billing/billing-admin-runbook.md`
- `../mysaas/my-saas/src/app/super-admin/layout.tsx`
- `../mysaas/my-saas/src/app/super-admin/plans/page.tsx`
- `../mysaas/my-saas/src/components/forms/plan-form.tsx`

## Task

Split the web product into public landing, authenticated user app, and a
separate admin console. Read the public pricing cards from the pricing
repository. Add admin navigation and pricing CRUD screens with server-side
admin gating, safe validation, reason capture, and audit writes. Keep the
existing guide route linked from all relevant surfaces.

## Acceptance Criteria

- `/` is a public landing page and contains no admin mutation controls.
- `/app` is the user workspace and preserves the existing foundation run flow.
- `/admin` has its own layout/navigation and links to pricing and payment
  settings rather than rendering inside the landing page.
- Active plans/options render from the repository, with a deterministic local
  fallback when configured explicitly.
- Admin mutations reject unauthorized requests and require a reason.
- The UI displays the active global payment model and supports the valid
  intervals for it; switching the admin policy changes public pricing and the
  user billing page.

## Verification & Status Update

Record typecheck, route smoke, and browser evidence in `step16-output.json`.
Use the local profile for deterministic checks and state its limitations.

## Don't

- Do not expose provider secrets or trust a client-supplied admin role.
- Do not hardcode pricing as the only source of truth in React components.
- Do not merge admin controls into the public landing route.
