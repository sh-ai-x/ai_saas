"""Fail-closed identity and tenant authorization contracts.

The boundary accepts the object returned by Better Auth's server-side
``auth.api.getSession`` call.  It intentionally does not parse browser
cookies, trust role/email fields from a request, or expose session tokens.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping


GOOGLE_ISSUER = "https://accounts.google.com"
SUPER_ADMIN = "super_admin"


class AuthorizationDenied(PermissionError):
    """A generic authorization failure safe to return from a protected route."""

    status_code = 403


class AuthenticationRequired(AuthorizationDenied):
    """No valid Better Auth session was supplied to a protected route."""

    status_code = 401


class OAuthCallbackError(ValueError):
    """A callback failed validation without revealing provider details."""

    status_code = 400


class AccountCollision(ValueError):
    """An identity cannot be linked without explicit authenticated consent."""


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset(
        {
            "tenant.read",
            "tenant.member.read",
            "tenant.member.manage",
            "admin.users.read",
            "admin.plans.write",
            "admin.credits.write",
        }
    ),
    Role.ADMIN: frozenset(
        {
            "tenant.read",
            "tenant.member.read",
            "admin.users.read",
            "admin.plans.write",
            "admin.credits.write",
        }
    ),
    Role.MEMBER: frozenset({"tenant.read"}),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expiry(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AuthenticationRequired("unauthenticated") from exc
    else:
        raise AuthenticationRequired("unauthenticated")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


@dataclass(frozen=True)
class GoogleIdentity:
    provider_subject: str
    email: str
    email_verified: bool
    issuer: str = GOOGLE_ISSUER
    display_name: str | None = None


@dataclass(frozen=True)
class GoogleOAuthCallback:
    state: str
    # Authorization codes are server-only input and must never appear in the
    # callback object's repr, audit event, telemetry, or response payload.
    code: str = field(repr=False)
    issuer: str = GOOGLE_ISSUER
    redirect_uri: str = ""

    def __repr__(self) -> str:
        return (
            "GoogleOAuthCallback(state_present=True, code_present=True, "
            f"issuer={self.issuer!r}, redirect_uri={self.redirect_uri!r})"
        )


@dataclass(frozen=True)
class OAuthTransaction:
    state: str = field(repr=False)
    issuer: str
    redirect_uri: str
    expires_at: datetime


class OAuthTransactionStore:
    """One-time server-side OAuth transaction storage."""

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._transactions: dict[str, OAuthTransaction] = {}

    def begin(
        self,
        state: str,
        redirect_uri: str,
        expires_at: datetime,
        issuer: str = GOOGLE_ISSUER,
    ) -> None:
        state = _required_text(state, "state")
        if state in self._transactions:
            raise OAuthCallbackError("oauth transaction already exists")
        self._transactions[state] = OAuthTransaction(
            state=state,
            issuer=_required_text(issuer, "issuer"),
            redirect_uri=_required_text(redirect_uri, "redirect_uri"),
            expires_at=_parse_expiry(expires_at),
        )

    def peek(self, state: str) -> OAuthTransaction | None:
        if not isinstance(state, str) or not state:
            return None
        return self._transactions.get(state)

    def consume(self, state: str) -> OAuthTransaction | None:
        if not isinstance(state, str) or not state:
            return None
        return self._transactions.pop(state, None)


class GoogleOAuthCallbackValidator:
    """Validate Google callback parameters and identity at the server boundary."""

    def __init__(
        self,
        transactions: OAuthTransactionStore,
        *,
        allowed_redirect_uris: set[str] | frozenset[str],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._transactions = transactions
        self._allowed_redirect_uris = frozenset(allowed_redirect_uris)
        self._clock = clock

    def validate(self, callback: GoogleOAuthCallback, identity: GoogleIdentity) -> GoogleIdentity:
        """Validate callback parameters and return only the safe identity.

        Code exchange is intentionally injected by the server adapter.  The
        validator never logs, serializes, or returns the authorization code.
        """

        self._validate_callback(callback)
        self._validate_identity(identity)
        if self._transactions.consume(callback.state) is None:
            raise OAuthCallbackError("invalid or replayed oauth state")
        return identity

    def validate_and_exchange(
        self,
        callback: GoogleOAuthCallback,
        exchange_code: Callable[[str, str], GoogleIdentity],
    ) -> GoogleIdentity:
        """Exchange a code inside the server adapter, then validate identity.

        ``exchange_code`` is injected so a client secret stays in the
        server-side provider adapter and never enters this contract's return
        value, repr, audit data, or browser-facing route payload.
        """

        transaction = self._validate_callback(callback)
        try:
            identity = exchange_code(callback.code, transaction.redirect_uri)
        except Exception:
            raise OAuthCallbackError("provider exchange failed") from None
        self._validate_identity(identity)
        if self._transactions.consume(callback.state) is None:
            raise OAuthCallbackError("invalid or replayed oauth state")
        return identity

    def _validate_callback(self, callback: GoogleOAuthCallback) -> OAuthTransaction:
        if not isinstance(callback, GoogleOAuthCallback):
            raise OAuthCallbackError("invalid oauth callback")
        if not isinstance(callback.code, str) or not callback.code.strip():
            raise OAuthCallbackError("invalid oauth callback")
        if not isinstance(callback.issuer, str) or not isinstance(callback.redirect_uri, str):
            raise OAuthCallbackError("invalid oauth callback")
        transaction = self._transactions.peek(callback.state)
        if transaction is None:
            raise OAuthCallbackError("invalid or replayed oauth state")
        if self._clock().astimezone(timezone.utc) >= transaction.expires_at:
            self._transactions.consume(callback.state)
            raise OAuthCallbackError("expired oauth transaction")
        if not hmac.compare_digest(callback.issuer, transaction.issuer):
            raise OAuthCallbackError("oauth issuer mismatch")
        if callback.redirect_uri not in self._allowed_redirect_uris:
            raise OAuthCallbackError("oauth redirect uri is not allowed")
        if not hmac.compare_digest(callback.redirect_uri, transaction.redirect_uri):
            raise OAuthCallbackError("oauth redirect uri mismatch")
        return transaction

    @staticmethod
    def _validate_identity(identity: GoogleIdentity) -> None:
        if not isinstance(identity, GoogleIdentity):
            raise OAuthCallbackError("invalid provider identity")
        if not isinstance(identity.issuer, str) or not isinstance(identity.provider_subject, str):
            raise OAuthCallbackError("invalid provider identity")
        if not isinstance(identity.email, str) or not isinstance(identity.email_verified, bool):
            raise OAuthCallbackError("invalid provider identity")
        if identity.issuer != GOOGLE_ISSUER:
            raise OAuthCallbackError("provider issuer mismatch")
        if not identity.provider_subject.strip() or not identity.email.strip():
            raise OAuthCallbackError("provider identity is incomplete")
        if identity.email_verified is not True:
            raise OAuthCallbackError("provider email is not verified")


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    email: str
    display_name: str | None = None
    status: str = "active"
    global_roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class TenantRecord:
    tenant_id: str
    name: str


@dataclass(frozen=True)
class Membership:
    user_id: str
    tenant_id: str
    role: Role


@dataclass(frozen=True)
class BetterAuthSession:
    """The non-secret subset of Better Auth's server-resolved session."""

    session_id: str
    user_id: str
    active_tenant_id: str | None
    expires_at: datetime

    @classmethod
    def from_better_auth(cls, payload: Mapping[str, Any]) -> "BetterAuthSession":
        if not isinstance(payload, Mapping):
            raise AuthenticationRequired("unauthenticated")
        session_value = payload.get("session", payload)
        user_value = payload.get("user", {})
        if not isinstance(session_value, Mapping) or not isinstance(user_value, Mapping):
            raise AuthenticationRequired("unauthenticated")
        session_id = session_value.get("id") or session_value.get("sessionId")
        user_id = session_value.get("userId") or user_value.get("id")
        tenant_id = (
            session_value.get("activeOrganizationId")
            or session_value.get("organizationId")
            or session_value.get("activeTenantId")
        )
        expiry = session_value.get("expiresAt") or session_value.get("expires_at")
        if not isinstance(session_id, str) or not session_id.strip():
            raise AuthenticationRequired("unauthenticated")
        if not isinstance(user_id, str) or not user_id.strip():
            raise AuthenticationRequired("unauthenticated")
        return cls(
            session_id=session_id,
            user_id=user_id,
            active_tenant_id=tenant_id if isinstance(tenant_id, str) and tenant_id else None,
            expires_at=_parse_expiry(expiry),
        )


@dataclass(frozen=True)
class RequestContext:
    user_id: str
    session_id: str
    active_tenant_id: str | None
    global_roles: frozenset[str]


class TenantBoundary:
    """Composition-root boundary for identity, tenant scope, and RBAC."""

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._users: dict[str, UserRecord] = {}
        self._tenants: dict[str, TenantRecord] = {}
        self._memberships: dict[tuple[str, str], Membership] = {}
        self._google_subjects: dict[tuple[str, str], str] = {}
        self._email_users: dict[str, str] = {}

    def add_user(
        self,
        user_id: str,
        email: str,
        *,
        display_name: str | None = None,
        global_roles: frozenset[str] | set[str] = frozenset(),
    ) -> UserRecord:
        user_id = _required_text(user_id, "user_id")
        email = _required_text(email, "email").lower()
        if user_id in self._users or email in self._email_users:
            raise ValueError("user already exists")
        user = UserRecord(user_id, email, display_name, global_roles=frozenset(global_roles))
        self._users[user_id] = user
        self._email_users[email] = user_id
        return user

    def add_tenant(self, tenant_id: str, name: str) -> TenantRecord:
        tenant = TenantRecord(_required_text(tenant_id, "tenant_id"), _required_text(name, "name"))
        if tenant.tenant_id in self._tenants:
            raise ValueError("tenant already exists")
        self._tenants[tenant.tenant_id] = tenant
        return tenant

    def add_membership(self, user_id: str, tenant_id: str, role: Role) -> Membership:
        if user_id not in self._users or tenant_id not in self._tenants:
            raise ValueError("membership references unknown identity or tenant")
        membership = Membership(user_id, tenant_id, Role(role))
        self._memberships[(user_id, tenant_id)] = membership
        return membership

    def link_google_identity(
        self,
        identity: GoogleIdentity,
        *,
        authenticated_user_id: str | None = None,
        confirm: bool = False,
    ) -> str:
        key = (identity.issuer, identity.provider_subject)
        linked = self._google_subjects.get(key)
        if linked:
            return linked
        existing = self._email_users.get(identity.email.lower())
        if existing:
            if authenticated_user_id != existing or not confirm:
                raise AccountCollision("explicit authenticated account linking is required")
            self._google_subjects[key] = existing
            return existing
        user_id = f"google-{uuid.uuid4().hex}"
        self.add_user(user_id, identity.email, display_name=identity.display_name)
        self._google_subjects[key] = user_id
        return user_id

    def authenticate(self, session: BetterAuthSession | Mapping[str, Any] | None) -> RequestContext:
        if session is None:
            raise AuthenticationRequired("unauthenticated")
        resolved = session if isinstance(session, BetterAuthSession) else BetterAuthSession.from_better_auth(session)
        if self._clock().astimezone(timezone.utc) >= resolved.expires_at:
            raise AuthenticationRequired("unauthenticated")
        user = self._users.get(resolved.user_id)
        if user is None or user.status != "active":
            raise AuthenticationRequired("unauthenticated")
        return RequestContext(
            user_id=user.user_id,
            session_id=resolved.session_id,
            active_tenant_id=resolved.active_tenant_id,
            global_roles=user.global_roles,
        )

    def require_tenant(self, context: RequestContext, tenant_id: str) -> Membership:
        if not isinstance(context, RequestContext):
            raise AuthenticationRequired("unauthenticated")
        if tenant_id not in self._tenants:
            raise AuthorizationDenied("tenant access denied")
        if context.active_tenant_id and context.active_tenant_id != tenant_id and SUPER_ADMIN not in context.global_roles:
            raise AuthorizationDenied("tenant access denied")
        membership = self._memberships.get((context.user_id, tenant_id))
        if membership is None and SUPER_ADMIN not in context.global_roles:
            raise AuthorizationDenied("tenant access denied")
        return membership or Membership(context.user_id, tenant_id, Role.OWNER)

    def require_permission(self, context: RequestContext, tenant_id: str, permission: str) -> Membership:
        membership = self.require_tenant(context, tenant_id)
        if SUPER_ADMIN in context.global_roles:
            return membership
        if permission not in ROLE_PERMISSIONS[membership.role]:
            raise AuthorizationDenied("permission denied")
        return membership

    def require_admin(self, context: RequestContext, tenant_id: str, permission: str) -> Membership:
        if not permission.startswith("admin."):
            raise ValueError("admin permission must use the admin namespace")
        return self.require_permission(context, tenant_id, permission)

    def user(self, user_id: str) -> UserRecord:
        try:
            return self._users[user_id]
        except KeyError as exc:
            raise AuthorizationDenied("user access denied") from exc

    def memberships_for_tenant(self, tenant_id: str) -> tuple[Membership, ...]:
        if tenant_id not in self._tenants:
            raise AuthorizationDenied("tenant access denied")
        return tuple(m for m in self._memberships.values() if m.tenant_id == tenant_id)
