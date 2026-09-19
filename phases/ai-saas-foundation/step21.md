Status: completed
Name: google-auth-runtime

## Read first

- `PRD.md` §9 and REQ-19–REQ-23
- `docs/sot/auth/google-oauth.md`
- `../mysaas/my-saas/src/auth.ts`
- `../mysaas/my-saas/src/app/api/auth/[...all]/route.ts`
- `apps/web/lib/admin-guard.ts`

## Task

Integrate Better Auth with the Drizzle identity schema and add the Next.js
server auth handler. Configure Google as a server-side social provider,
expose a safe session projection, add sign-out, and connect admin protection
to a server-validated admin role while preserving the explicit local/test
guard. Add fail-closed environment validation so production cannot issue a
Google redirect or run with an incomplete secret/database configuration.

## Acceptance Criteria

- `/api/auth/[...all]` handles the Better Auth flow and uses the Drizzle
  adapter with the `app_user`, `session`, `account`, and `verification`
  mappings.
- Google client ID/secret and Better Auth secret are read only at runtime;
  missing production configuration returns a safe configuration error.
- Session lookup returns only user id, email, display name, role, and expiry;
  provider tokens and cookies are never included in JSON.
- Admin API authorization accepts a server session with an admin role and
  rejects an ordinary Google-authenticated user.
- Local/test mode remains runnable without `DATABASE_URL` or Google secrets.

## Verification & Status Update

Record route contract tests, configuration matrix results, and exact command
metadata in `step21-output.json` before marking the step complete.

## Don't

- Do not implement a second custom OAuth protocol beside Better Auth.
- Do not put a client secret, access token, refresh token, or ID token in a
  client bundle, response body, fixture, or log.
- Do not grant admin access based on `@google.com` or any email domain.
