---
id: google-oauth
category: AUTH
title: Google OAuth
summary: Configure the server-side authorization-code flow and browser callback.
---
# Google OAuth

## 1. Create OAuth credentials

In Google Cloud Console, create an OAuth 2.0 Web application client and add the
exact callback URL below. Never put the client secret in `apps/web`.

```text
http://127.0.0.1:3000/auth/callback
```

## 2. Enable the provider

```bash
AUTH_PROVIDER=google
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=server-only-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:3000/auth/callback
```

`GET /v1/auth/google/start` creates one-time state and returns the Google
authorization URL. The Next.js callback route POSTs the code to the API.

## 3. Server-side verification

The API exchanges the code, verifies Google issuer, audience, subject, expiry,
and verified email, then sets an HttpOnly session cookie. React never receives
the authorization code, access token, or ID token.

## 4. Verify

```bash
python3 -m unittest tests/test_google_oauth_provider.py
```

Use a test account first. Replay the callback or change `state` to confirm the
API rejects it without creating a session.
