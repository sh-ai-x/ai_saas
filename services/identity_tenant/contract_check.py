"""Executable identity and tenant contract checks used by intent integrity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .boundary import (
    AuthorizationDenied,
    BetterAuthSession,
    GoogleIdentity,
    GoogleOAuthCallback,
    GoogleOAuthCallbackValidator,
    OAuthCallbackError,
    OAuthTransactionStore,
    Role,
    TenantBoundary,
)


def run_contract_checks() -> list[str]:
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    transactions = OAuthTransactionStore(clock=lambda: now)
    transactions.begin("integrity-state", "https://app.example.test/callback", now + timedelta(minutes=5))
    validator = GoogleOAuthCallbackValidator(
        transactions,
        allowed_redirect_uris={"https://app.example.test/callback"},
        clock=lambda: now,
    )
    identity = validator.validate(
        GoogleOAuthCallback(
            state="integrity-state",
            code="integrity-code",
            issuer="https://accounts.google.com",
            redirect_uri="https://app.example.test/callback",
        ),
        GoogleIdentity("google-integrity-subject", "integrity@example.test", True),
    )
    if identity.provider_subject != "google-integrity-subject":
        raise AssertionError("google identity contract did not preserve provider subject")
    try:
        validator.validate(
            GoogleOAuthCallback(
                state="integrity-state",
                code="integrity-code",
                issuer="https://accounts.google.com",
                redirect_uri="https://app.example.test/callback",
            ),
            identity,
        )
    except OAuthCallbackError:
        pass
    else:
        raise AssertionError("oauth state replay was accepted")

    boundary = TenantBoundary(clock=lambda: now)
    boundary.add_user("integrity-admin", "admin@example.test")
    boundary.add_user("integrity-member", "member@example.test")
    boundary.add_tenant("integrity-tenant-a", "A")
    boundary.add_tenant("integrity-tenant-b", "B")
    boundary.add_membership("integrity-admin", "integrity-tenant-a", Role.ADMIN)
    boundary.add_membership("integrity-member", "integrity-tenant-b", Role.MEMBER)
    context = boundary.authenticate(
        BetterAuthSession(
            session_id="integrity-session",
            user_id="integrity-admin",
            active_tenant_id="integrity-tenant-a",
            expires_at=now + timedelta(hours=1),
        )
    )
    boundary.require_admin(context, "integrity-tenant-a", "admin.users.read")
    try:
        boundary.require_admin(context, "integrity-tenant-b", "admin.users.read")
    except AuthorizationDenied:
        pass
    else:
        raise AssertionError("cross-tenant admin access was accepted")
    return ["validated Google callback and one-time state", "validated tenant RBAC denial"]
