from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from services.admin_operations import (
    AdminOperations,
    AuditLog,
    InMemoryCreditLedger,
    InMemoryEntitlements,
    ReasonRequired,
)
from services.identity_tenant import (
    AccountCollision,
    AuthenticationRequired,
    AuthorizationDenied,
    BetterAuthSession,
    GoogleIdentity,
    GoogleOAuthCallback,
    GoogleOAuthCallbackValidator,
    OAuthCallbackError,
    OAuthTransactionStore,
    ProtectedRouteChecks,
    Role,
    TenantBoundary,
)


NOW = datetime(2026, 9, 18, 0, 0, tzinfo=timezone.utc)


def make_boundary() -> TenantBoundary:
    boundary = TenantBoundary(clock=lambda: NOW)
    boundary.add_user("user-a", "a@example.test")
    boundary.add_user("user-b", "b@example.test")
    boundary.add_user("user-c", "c@example.test")
    boundary.add_tenant("tenant-a", "Tenant A")
    boundary.add_tenant("tenant-b", "Tenant B")
    boundary.add_membership("user-a", "tenant-a", Role.ADMIN)
    boundary.add_membership("user-b", "tenant-b", Role.ADMIN)
    boundary.add_membership("user-c", "tenant-a", Role.MEMBER)
    return boundary


def session_for(user_id: str, tenant_id: str) -> BetterAuthSession:
    return BetterAuthSession(
        session_id=f"session-{user_id}",
        user_id=user_id,
        active_tenant_id=tenant_id,
        expires_at=NOW + timedelta(hours=1),
    )


class GoogleOAuthContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = OAuthTransactionStore(clock=lambda: NOW)
        self.validator = GoogleOAuthCallbackValidator(
            self.transactions,
            allowed_redirect_uris={"https://app.example.test/auth/google/callback"},
            clock=lambda: NOW,
        )

    def callback(self, **overrides: object) -> GoogleOAuthCallback:
        values: dict[str, object] = {
            "state": "state-123",
            "code": "one-time-code",
            "issuer": "https://accounts.google.com",
            "redirect_uri": "https://app.example.test/auth/google/callback",
        }
        values.update(overrides)
        return GoogleOAuthCallback(**values)  # type: ignore[arg-type]

    def identity(self) -> GoogleIdentity:
        return GoogleIdentity(
            provider_subject="google-subject-123",
            email="user@example.test",
            email_verified=True,
            issuer="https://accounts.google.com",
        )

    def test_valid_callback_consumes_state_and_returns_identity_without_code(self) -> None:
        self.transactions.begin("state-123", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        result = self.validator.validate(self.callback(), self.identity())
        self.assertEqual(result.provider_subject, "google-subject-123")
        self.assertNotIn("one-time-code", repr(result))

        with self.assertRaises(OAuthCallbackError):
            self.validator.validate(self.callback(), self.identity())

    def test_code_exchange_is_server_side_and_provider_failure_is_generic(self) -> None:
        self.transactions.begin("state-123", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        seen: list[tuple[str, str]] = []

        def exchange(code: str, redirect_uri: str) -> GoogleIdentity:
            seen.append((code, redirect_uri))
            return self.identity()

        self.validator.validate_and_exchange(self.callback(), exchange)
        self.assertEqual(seen, [("one-time-code", "https://app.example.test/auth/google/callback")])

        self.transactions.begin("state-failure", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        with self.assertRaisesRegex(OAuthCallbackError, "provider exchange failed"):
            self.validator.validate_and_exchange(
                self.callback(state="state-failure"),
                lambda _code, _redirect: (_ for _ in ()).throw(RuntimeError("provider detail")),
            )

    def test_invalid_state_redirect_issuer_and_expiry_fail_closed(self) -> None:
        self.transactions.begin("state-123", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        for callback in (
            self.callback(state="wrong-state"),
            self.callback(redirect_uri="https://evil.example.test/callback"),
            self.callback(issuer="https://evil.example.test"),
        ):
            with self.assertRaises(OAuthCallbackError):
                self.validator.validate(callback, self.identity())

        expired = OAuthTransactionStore(clock=lambda: NOW)
        expired.begin("expired", "https://app.example.test/auth/google/callback", NOW - timedelta(seconds=1))
        with self.assertRaises(OAuthCallbackError):
            GoogleOAuthCallbackValidator(
                expired,
                allowed_redirect_uris={"https://app.example.test/auth/google/callback"},
                clock=lambda: NOW,
            ).validate(self.callback(state="expired"), self.identity())

        self.transactions.begin("malformed", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        with self.assertRaises(OAuthCallbackError):
            self.validator.validate(self.callback(state="malformed", issuer=object()), self.identity())

    def test_unverified_identity_and_email_collision_require_explicit_link(self) -> None:
        self.transactions.begin("state-123", "https://app.example.test/auth/google/callback", NOW + timedelta(minutes=5))
        with self.assertRaises(OAuthCallbackError):
            self.validator.validate(
                self.callback(),
                GoogleIdentity(
                    provider_subject="google-subject-123",
                    email="user@example.test",
                    email_verified=False,
                    issuer="https://accounts.google.com",
                ),
            )

        boundary = TenantBoundary(clock=lambda: NOW)
        boundary.add_user("existing", "user@example.test")
        identity = self.identity()
        with self.assertRaises(AccountCollision):
            boundary.link_google_identity(identity)
        self.assertEqual(boundary.link_google_identity(identity, authenticated_user_id="existing", confirm=True), "existing")


class TenantAndRouteAuthorizationTests(unittest.TestCase):
    def test_better_auth_fields_are_resolved_server_side_and_email_is_not_admin(self) -> None:
        boundary = make_boundary()
        raw = {
            "session": {
                "id": "session-user-a",
                "userId": "user-c",
                "activeOrganizationId": "tenant-a",
                "expiresAt": "2026-09-18T01:00:00Z",
                "token": "browser-cookie-value",
                "role": "super_admin",
            },
            "user": {"id": "user-c", "email": "c@example.test"},
        }
        context = boundary.authenticate(raw)
        self.assertEqual(context.user_id, "user-c")
        self.assertNotIn("browser-cookie-value", repr(context))
        with self.assertRaises(AuthorizationDenied):
            boundary.require_admin(context, "tenant-a", "admin.users.read")

    def test_member_cannot_access_admin_route_or_another_tenant(self) -> None:
        boundary = make_boundary()
        context = boundary.authenticate(session_for("user-c", "tenant-a"))
        with self.assertRaises(AuthorizationDenied):
            boundary.require_admin(context, "tenant-a", "admin.users.read")
        with self.assertRaises(AuthorizationDenied):
            boundary.require_tenant(context, "tenant-b")

    def test_tenant_admin_cannot_cross_tenant_even_when_target_user_exists(self) -> None:
        boundary = make_boundary()
        context = boundary.authenticate(session_for("user-a", "tenant-a"))
        with self.assertRaises(AuthorizationDenied):
            boundary.require_admin(context, "tenant-b", "admin.users.read")

    def test_expired_and_missing_sessions_are_unauthenticated(self) -> None:
        boundary = make_boundary()
        with self.assertRaises(AuthenticationRequired) as missing:
            boundary.authenticate(None)
        self.assertEqual(missing.exception.status_code, 401)
        with self.assertRaises(AuthorizationDenied):
            boundary.authenticate(
                BetterAuthSession(
                    session_id="expired",
                    user_id="user-a",
                    active_tenant_id="tenant-a",
                    expires_at=NOW - timedelta(seconds=1),
                )
            )

    def test_protected_route_adapter_resolves_session_before_scope_check(self) -> None:
        boundary = make_boundary()
        routes = ProtectedRouteChecks(boundary)
        session = {
            "session": {
                "id": "session-user-a",
                "userId": "user-a",
                "activeOrganizationId": "tenant-a",
                "expiresAt": "2026-09-18T01:00:00Z",
            },
            "user": {"id": "user-a", "email": "a@example.test"},
        }
        context = routes.admin(session, "tenant-a", "admin.users.read")
        self.assertEqual(context.user_id, "user-a")
        with self.assertRaises(AuthorizationDenied):
            routes.admin(session, "tenant-b", "admin.users.read")


class AdminOperationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.boundary = make_boundary()
        self.actor = self.boundary.authenticate(session_for("user-a", "tenant-a"))
        self.entitlements = InMemoryEntitlements({"user-c": "free"})
        self.ledger = InMemoryCreditLedger({"user-c": 10})
        self.audit = AuditLog()
        self.admin = AdminOperations(self.boundary, self.entitlements, self.ledger, self.audit, clock=lambda: NOW)

    def test_plan_mutation_requires_reason_and_records_before_after(self) -> None:
        with self.assertRaises(ReasonRequired):
            self.admin.change_plan(self.actor, "tenant-a", "user-c", "pro", reason=" ")

        result = self.admin.change_plan(
            self.actor,
            "tenant-a",
            "user-c",
            "pro",
            reason="approved support upgrade",
            correlation_id="corr-plan-1",
        )
        self.assertEqual(result.after["plan"], "pro")
        event = self.audit.events()[0]
        self.assertEqual(event.before["plan"], "free")
        self.assertEqual(event.after["plan"], "pro")
        self.assertEqual(event.actor_user_id, "user-a")
        self.assertEqual(event.reason, "approved support upgrade")
        self.assertEqual(event.correlation_id, "corr-plan-1")

    def test_credit_adjustment_uses_ledger_port_and_is_audited(self) -> None:
        result = self.admin.adjust_credits(
            self.actor,
            "tenant-a",
            "user-c",
            5,
            reason="make-good for failed run",
            correlation_id="corr-credit-1",
        )
        self.assertEqual(result.after["credit_balance"], 15)
        self.assertEqual(self.ledger.adjustment_calls, [("user-c", 5, "make-good for failed run")])
        self.assertEqual(self.audit.events()[0].action, "credits.adjust")

    def test_admin_operation_denies_cross_tenant_target_before_mutation(self) -> None:
        with self.assertRaises(AuthorizationDenied):
            self.admin.change_plan(self.actor, "tenant-b", "user-b", "pro", reason="not allowed")
        self.assertEqual(self.entitlements.plans, {"user-c": "free"})
        self.assertEqual(self.audit.events(), ())

    def test_audit_log_is_append_only(self) -> None:
        self.admin.change_plan(self.actor, "tenant-a", "user-c", "pro", reason="approved")
        events = self.audit.events()
        with self.assertRaises(TypeError):
            events[0].before["plan"] = "enterprise"  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
