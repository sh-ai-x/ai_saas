"""Server-side Google OAuth authorization-code client.

The client is deliberately small and dependency-free.  It keeps the client
secret and tokens inside the composition root and returns only the validated
identity contract to the identity boundary.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .boundary import GOOGLE_ISSUER, GoogleIdentity


GoogleRequest = Callable[
    [str, str, Mapping[str, str], Mapping[str, str] | None], dict[str, Any]
]


def _request_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    form: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    body = None if form is None else urlencode(form).encode("utf-8")
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=15) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google provider request failed") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Google provider response is invalid")
    if "error" in value:
        raise RuntimeError("Google provider rejected the request")
    return value


@dataclass(frozen=True)
class GoogleAuthorization:
    state: str
    redirect_uri: str
    authorization_url: str


class GoogleOAuthProvider:
    """Google OAuth client with issuer, audience, expiry and email checks."""

    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    tokeninfo_endpoint = "https://oauth2.googleapis.com/tokeninfo"
    userinfo_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        request_json: GoogleRequest = _request_json,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._request_json = request_json
        self._now = now

    def authorization_url(self, state: str) -> GoogleAuthorization:
        if not state.strip():
            raise ValueError("oauth state is required")
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        return GoogleAuthorization(state, self._redirect_uri, f"{self.authorization_endpoint}?{query}")

    def exchange_code(self, code: str, redirect_uri: str) -> GoogleIdentity:
        if redirect_uri != self._redirect_uri:
            raise RuntimeError("Google redirect URI mismatch")
        token = self._request_json(
            "POST",
            self.token_endpoint,
            {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            {
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        access_token = token.get("access_token")
        id_token = token.get("id_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Google access token is missing")
        if not isinstance(id_token, str) or not id_token:
            raise RuntimeError("Google ID token is missing")

        claims = self._request_json(
            "GET",
            f"{self.tokeninfo_endpoint}?{urlencode({'id_token': id_token})}",
            {"Accept": "application/json"},
            None,
        )
        issuer = str(claims.get("iss") or "")
        audience = str(claims.get("aud") or "")
        subject = str(claims.get("sub") or "")
        expiry = claims.get("exp")
        if issuer not in {GOOGLE_ISSUER, "accounts.google.com"}:
            raise RuntimeError("Google issuer is invalid")
        if audience != self._client_id or not subject:
            raise RuntimeError("Google audience or subject is invalid")
        try:
            if float(expiry) <= self._now():
                raise RuntimeError("Google ID token is expired")
        except (TypeError, ValueError):
            raise RuntimeError("Google ID token expiry is invalid") from None

        userinfo = self._request_json(
            "GET",
            self.userinfo_endpoint,
            {"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
            None,
        )
        email = userinfo.get("email") or claims.get("email")
        verified = userinfo.get("email_verified", claims.get("email_verified"))
        if isinstance(verified, str):
            verified = verified.lower() == "true"
        if not isinstance(email, str) or not isinstance(verified, bool):
            raise RuntimeError("Google verified email is missing")
        return GoogleIdentity(
            provider_subject=subject,
            email=email,
            email_verified=verified,
            issuer=GOOGLE_ISSUER,
            display_name=str(userinfo.get("name") or claims.get("name") or "Google user"),
        )
