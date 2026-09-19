Status: completed
Name: google-auth-surfaces

## Read first

- `PRD.md` §9 and REQ-20–REQ-23
- `docs/sot/auth/google-oauth.md`
- `../mysaas/my-saas/src/components/auth/auth-form.tsx`
- `apps/web/app/page.tsx`
- `apps/web/app/app/page.tsx`
- `apps/web/app/admin/layout.tsx`

## Task

Add a dedicated sign-in surface and connect it to the public landing, user
workspace, billing, and admin navigation. Implement Google sign-in, sign-out,
loading, callback failure, and unauthenticated states with a safe session
projection. Keep the landing page separate from the authenticated workspace
and preserve the admin console's policy/pricing navigation.

## Acceptance Criteria

- `/login` clearly starts Google sign-in and does not render secrets or raw
  provider response data.
- Authenticated users can see their safe profile/session state and sign out;
  unauthenticated users receive a clear login path for protected workspace
  actions.
- Admin navigation remains separate and ordinary users cannot see or mutate
  admin operations merely because they used Google login.
- Callback/provider errors are rendered as safe, retryable categories with no
  authorization code in the URL or UI.
- Existing landing, billing mode, and pricing pages remain functional in the
  local credential-free profile.

## Verification & Status Update

Record browser route checks and console-error results in `step22-output.json`.

## Don't

- Do not turn the public landing page into the admin page.
- Do not put provider SDK calls in browser code when the server handler can
  perform the operation.
- Do not make billing entitlement follow the presence of a session alone.
