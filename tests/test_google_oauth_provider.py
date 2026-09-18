from __future__ import annotations

import unittest

from services.identity_tenant.google_provider import GoogleOAuthProvider


class GoogleProviderTests(unittest.TestCase):
    def test_authorization_and_server_side_exchange(self) -> None:
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def request(method, url, headers, form):
            calls.append((method, url, form))
            if url.endswith("/token"):
                return {"access_token": "access-token", "id_token": "id-token"}
            if "/tokeninfo?" in url:
                return {"iss": "https://accounts.google.com", "aud": "client-id", "sub": "google-sub", "exp": "2000"}
            return {"sub": "google-sub", "email": "person@example.com", "email_verified": True, "name": "Person"}

        provider = GoogleOAuthProvider(
            client_id="client-id",
            client_secret="server-secret",
            redirect_uri="http://127.0.0.1:3000/auth/callback",
            request_json=request,
            now=lambda: 1000,
        )
        authorization = provider.authorization_url("state-12345678")
        self.assertIn("client_id=client-id", authorization.authorization_url)
        identity = provider.exchange_code("one-time-code", authorization.redirect_uri)
        self.assertEqual(identity.provider_subject, "google-sub")
        self.assertTrue(identity.email_verified)
        self.assertEqual(calls[0][2]["client_secret"], "server-secret")

    def test_invalid_audience_is_rejected(self) -> None:
        def request(method, url, headers, form):
            if url.endswith("/token"):
                return {"access_token": "access-token", "id_token": "id-token"}
            if "/tokeninfo?" in url:
                return {"iss": "https://accounts.google.com", "aud": "wrong-client", "sub": "google-sub", "exp": "2000"}
            return {}

        provider = GoogleOAuthProvider(
            client_id="client-id",
            client_secret="server-secret",
            redirect_uri="http://127.0.0.1:3000/auth/callback",
            request_json=request,
            now=lambda: 1000,
        )
        with self.assertRaises(RuntimeError):
            provider.exchange_code("one-time-code", "http://127.0.0.1:3000/auth/callback")


if __name__ == "__main__":
    unittest.main()
