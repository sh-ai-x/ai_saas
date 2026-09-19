Status: completed
Name: google-oauth-provider

Task:
Implement the server-side Google authorization-code client, callback validation,
token/userinfo verification, session cookie, and web callback route. Keep the
local mock flow available when `AUTH_PROVIDER=local-mock`.

Acceptance:
- The configured provider returns a Google authorization URL with exact
  redirect URI, state, nonce, and safe scopes.
- Callback exchanges the code server-side, validates issuer/audience/subject,
  verified email, state, expiry, and one-time use, then creates a session.
- Browser callback never exposes the code or token to client JavaScript.
- Provider timeout/error and account collision fail without partial state.

Verification:
```bash
python3 -m unittest tests/test_google_oauth_provider.py
```
