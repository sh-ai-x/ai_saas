"""Executable privileged-operation and audit checks used by intent integrity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.identity_tenant import AuthorizationDenied, BetterAuthSession, Role, TenantBoundary

from .service import AdminOperations, AuditLog, InMemoryCreditLedger, InMemoryEntitlements, ReasonRequired


def run_contract_checks() -> list[str]:
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    boundary = TenantBoundary(clock=lambda: now)
    boundary.add_user("integrity-admin", "admin-ops@example.test")
    boundary.add_user("integrity-target", "target-ops@example.test")
    boundary.add_user("integrity-other", "other-ops@example.test")
    boundary.add_tenant("integrity-tenant-a", "A")
    boundary.add_tenant("integrity-tenant-b", "B")
    boundary.add_membership("integrity-admin", "integrity-tenant-a", Role.ADMIN)
    boundary.add_membership("integrity-target", "integrity-tenant-a", Role.MEMBER)
    boundary.add_membership("integrity-other", "integrity-tenant-b", Role.MEMBER)
    actor = boundary.authenticate(
        BetterAuthSession(
            session_id="integrity-admin-session",
            user_id="integrity-admin",
            active_tenant_id="integrity-tenant-a",
            expires_at=now + timedelta(hours=1),
        )
    )
    entitlements = InMemoryEntitlements({"integrity-target": "free"})
    ledger = InMemoryCreditLedger({"integrity-target": 1})
    audit = AuditLog()
    operations = AdminOperations(boundary, entitlements, ledger, audit, clock=lambda: now)
    try:
        operations.change_plan(actor, "integrity-tenant-a", "integrity-target", "pro", reason=" ")
    except ReasonRequired:
        pass
    else:
        raise AssertionError("reason-less plan mutation was accepted")
    operations.change_plan(
        actor,
        "integrity-tenant-a",
        "integrity-target",
        "pro",
        reason="integrity check",
        correlation_id="integrity-correlation",
    )
    event = audit.events()[0]
    if event.before["plan"] != "free" or event.after["plan"] != "pro":
        raise AssertionError("audit event did not capture plan before/after")
    try:
        operations.adjust_credits(actor, "integrity-tenant-b", "integrity-other", 1, reason="wrong scope")
    except AuthorizationDenied:
        pass
    else:
        raise AssertionError("cross-tenant admin mutation was accepted")
    return ["validated reason-required admin mutation and audit snapshots"]

