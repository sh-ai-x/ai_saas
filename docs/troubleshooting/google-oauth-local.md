# Google OAuth local troubleshooting

This runbook covers the local Docker setup at `http://localhost:3000`.
It documents the incident where Google sign-in intermittently failed with a
redirect URI message and sign-out did not clear the logged-in session.

## Symptoms

- Google sign-in shows `Google sign-in could not be started. Check the configured redirect URI.`
- The same browser sometimes reaches different login behavior on
  `localhost:3000`.
- Clicking **Sign out** returns to the home page, but the user is still shown
  as signed in after the page reloads.

## Root cause

Two independent configuration problems made the flow appear intermittent.

### 1. Two servers owned port 3000

A native Next.js process was listening on IPv6 `localhost` (`[::1]:3000`) at
the same time as the Docker web container was publishing `0.0.0.0:3000`.
Depending on how `localhost` resolved, the browser reached a different
process. The native process did not have the same Docker runtime configuration,
so Better Auth generated a redirect URI from a different environment.

The registered local OAuth values must stay consistent:

```text
Browser origin:     http://localhost:3000
Better Auth URL:    http://localhost:3000
Google redirect:    http://localhost:3000/api/auth/callback/google
```

`http://127.0.0.1:3000` is not interchangeable with `http://localhost:3000`
for Google OAuth or Better Auth origin checks.

### 2. The Google flag was available at runtime but missing from the browser bundle

`NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` is read by client-side React code. Next.js
replaces `NEXT_PUBLIC_*` variables while building the client bundle; setting
the variable only in the container's runtime `environment` does not update an
already-built bundle.

The old Docker build had this mismatch:

```text
Docker runtime:  NEXT_PUBLIC_GOOGLE_AUTH_ENABLED=true
Browser bundle:  NEXT_PUBLIC_GOOGLE_AUTH_ENABLED was empty
```

The session control consequently selected `/api/auth/local/sign-out`. That
test-only route clears `ai_saas_demo_session`, but a Google login is stored in
Better Auth cookies (`better-auth.session_token`, `better-auth.session_data`,
and `better-auth.dont_remember`). Those cookies remained valid, so the user
appeared to log back in immediately.

## Resolution

The Docker client build now receives the public flag explicitly:

- `apps/web/Dockerfile` declares a builder `ARG` and exposes it as a builder
  `ENV` before `next build`.
- `docker/prod/compose.yaml` passes
  `NEXT_PUBLIC_GOOGLE_AUTH_ENABLED` as a build argument, while retaining the
  runtime environment variable for server-rendered configuration.
- `apps/web/tests/docker-google-auth-build.test.ts` prevents the Dockerfile
  and Compose build argument from drifting apart.

The session control source remains provider-aware. With Google enabled, the
production bundle now calls `authClient.signOut()`, which reaches
`/api/auth/sign-out` and expires the Better Auth session cookies.

## Recovery procedure

Run these commands from the repository root. Use the same ignored root `.env`
file for the Docker stack; `apps/web/.env.local` is not automatically copied
into the Docker build context.

```bash
pnpm docker:local
```

If a stale native server is suspected, identify the exact listener before
stopping it:

```bash
lsof -nP -iTCP:3000 -sTCP:LISTEN
docker ps --filter publish=3000
```

Stop only the unrelated native Next process. Do not stop the Docker web
container if it is the intended owner of port 3000. Then confirm that the web
container is healthy:

```bash
docker ps --filter name=ai-saas-foundation-web-1
```

The expected state includes `0.0.0.0:3000->3000/tcp` and `healthy`.

## Verification checklist

### Verify login configuration

The login page must report that Google OAuth is configured:

```bash
curl -fsS http://localhost:3000/login \
  | grep -o 'Google OAuth is configured[^<]*'
```

Start the OAuth flow and inspect only the generated redirect URI. Do not log
authorization codes or tokens:

```bash
curl -fsS -X POST http://localhost:3000/api/auth/sign-in/social \
  -H 'content-type: application/json' \
  -H 'origin: http://localhost:3000' \
  --data '{"provider":"google","callbackURL":"/app"}'
```

The response should contain an authorization URL whose decoded
`redirect_uri` is exactly:

```text
http://localhost:3000/api/auth/callback/google
```

### Verify logout

```bash
curl -i -X POST http://localhost:3000/api/auth/sign-out \
  -H 'content-type: application/json' \
  -H 'origin: http://localhost:3000' \
  --data '{}'
```

Expected result:

- HTTP `200 OK`
- response body `{"success":true}`
- `Set-Cookie` headers expiring the Better Auth session cookies
- a subsequent `/api/auth/session` response with `{"session":null}`

### Verify the build-time flag

```bash
docker compose --env-file .env \
  -f docker/prod/compose.yaml config --format json \
  | jq -r '.services.web.build.args.NEXT_PUBLIC_GOOGLE_AUTH_ENABLED'
```

Expected output is `true`. Changing the environment file without rebuilding
the web image is insufficient for a `NEXT_PUBLIC_*` client variable.

## Triage table

| Symptom | Likely cause | Corrective action |
|---|---|---|
| `redirect_uri_mismatch` | Google Cloud URI differs by host, port, path, scheme, or slash | Register `http://localhost:3000/api/auth/callback/google` exactly and use `localhost` consistently |
| Login behavior changes between attempts | Native Next and Docker both listen on port 3000 | Keep one owner for port 3000 and recreate the intended Docker web service |
| Login page says Google is not configured | Server env is missing or the old web container is still running | Update root `.env`, run `pnpm docker:local`, and confirm the container is healthy |
| Login works but sign-out appears to do nothing | Old client bundle selected the local demo sign-out route | Rebuild the web image with the public build argument and force-recreate the web container |
| `127.0.0.1` fails while `localhost` works | Origin/redirect URI mismatch | Use the registered `localhost` origin, not a substitute host |

## Prevention

- Do not run the native dev server and Docker web service on the same port.
- Treat `NEXT_PUBLIC_*` values as build inputs, not runtime-only values.
- Rebuild and recreate the web service after changing client-visible auth
  configuration.
- Keep the Google redirect URI, `BETTER_AUTH_URL`, browser URL, and Docker
  port mapping on the same origin.
- Run the web contract tests before opening a PR:

```bash
pnpm --filter ai-saas-foundation-web test:all
```
