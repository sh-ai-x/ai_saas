# Google OAuth

## 1. Create credentials

In Google Cloud Console, create an OAuth 2.0 Web application client. Register
the exact callback URL for the web origin:

```text
http://127.0.0.1:3000/auth/callback
```

For a deployed preview, register the preview URL separately. Do not use a
wildcard redirect URI.

## 2. Configure the server

Copy the example and replace values outside Git:

```bash
cp config/profiles/google-sandbox.example.env .env
export APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
python3 -m foundation.config --env-file .env --profile free-portfolio
```

The required settings are `AUTH_PROVIDER=google`, client ID, client secret,
and exact redirect URI. The Next.js app receives only the authorization URL.

## 3. Flow and security

1. `GET /v1/auth/google/start` creates one-time state and an authorization URL.
2. Google redirects to the Next.js `/auth/callback` route.
3. The route POSTs the code to the API; Python exchanges it server-side.
4. Google issuer, audience, subject, expiry, and verified email are checked.
5. The API creates a server-owned session and sets an HttpOnly cookie.

Authorization codes and tokens are never returned to React, logs, traces, or
the browser URL after the callback redirect.

## 4. Verify

```bash
python3 -m unittest tests/test_google_oauth_provider.py
```

Use a test account first. Replay the callback or change `state` to confirm the
API rejects it without creating a session.
