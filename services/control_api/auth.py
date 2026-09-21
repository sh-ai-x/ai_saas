"""Small tenant authentication boundary for the control plane.

Local Lite deliberately permits an explicit ``X-Tenant-ID`` header so the
service can run without a credential. Any non-local deployment must provide
``CONTROL_API_TOKEN_SECRET`` and use a signed bearer token instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass


class AuthenticationError(PermissionError):
    """Raised when a request cannot be mapped to an authenticated tenant."""


_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class TenantAuthenticator:
    secret: bytes | None = None
    allow_insecure_local: bool = False
    token_ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.secret is not None and len(self.secret) < 16:
            raise ValueError("CONTROL_API_TOKEN_SECRET must be at least 16 bytes")

    def issue(self, tenant_id: str, *, now: int | None = None) -> str:
        self._validate_tenant(tenant_id)
        if not self.secret:
            raise AuthenticationError("signed tokens require CONTROL_API_TOKEN_SECRET")
        issued = int(time.time() if now is None else now)
        payload = _encode(json.dumps({"tenant_id": tenant_id, "exp": issued + self.token_ttl_seconds}, separators=(",", ":")).encode())
        signature = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"Bearer {payload}.{signature}"

    def authenticate(self, authorization: str | None, tenant_header: str | None, *, now: int | None = None) -> str:
        if self.secret:
            if not authorization or not authorization.startswith("Bearer "):
                raise AuthenticationError("signed bearer authentication is required")
            token = authorization[7:].strip()
            try:
                payload_part, signature = token.split(".", 1)
                expected = hmac.new(self.secret, payload_part.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(expected, signature):
                    raise AuthenticationError("invalid bearer token")
                payload = json.loads(_decode(payload_part))
                tenant_id = str(payload["tenant_id"])
                if int(payload["exp"]) <= int(time.time() if now is None else now):
                    raise AuthenticationError("bearer token expired")
            except (AuthenticationError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                if isinstance(exc, AuthenticationError):
                    raise
                raise AuthenticationError(f"invalid bearer token: {type(exc).__name__}: {exc}") from exc
            self._validate_tenant(tenant_id)
            if tenant_header and tenant_header != tenant_id:
                raise AuthenticationError("tenant header does not match bearer token")
            return tenant_id

        if not self.allow_insecure_local:
            raise AuthenticationError("CONTROL_API_TOKEN_SECRET is not configured")
        if not tenant_header:
            raise AuthenticationError("X-Tenant-ID is required for Local Lite")
        self._validate_tenant(tenant_header)
        return tenant_header

    @staticmethod
    def _validate_tenant(tenant_id: str) -> None:
        if not _TENANT.fullmatch(tenant_id):
            raise AuthenticationError("invalid tenant identifier")
