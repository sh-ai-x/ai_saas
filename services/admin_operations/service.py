"""Server-side admin use cases with tenant scope and audit evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

from services.identity_tenant import AuthorizationDenied, RequestContext, TenantBoundary


class ReasonRequired(ValueError):
    """A privileged mutation cannot be performed without an operator reason."""


class EntitlementPort(Protocol):
    def current_plan(self, user_id: str) -> str: ...

    def transition_plan(self, user_id: str, plan: str, *, reason: str) -> str: ...


class CreditLedgerPort(Protocol):
    def current_balance(self, user_id: str) -> int: ...

    def adjust_credits(self, user_id: str, amount: int, *, reason: str) -> int: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _freeze(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))


def _reason(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReasonRequired("a non-empty reason is required")
    normalized = value.strip()
    if len(normalized) > 500:
        raise ReasonRequired("reason is too long")
    return normalized


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    occurred_at: datetime
    actor_user_id: str
    actor_tenant_id: str
    action: str
    target_type: str
    target_id: str
    reason: str
    before: Mapping[str, object]
    after: Mapping[str, object]
    source: str
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", _freeze(self.before))
        object.__setattr__(self, "after", _freeze(self.after))


class AuditLog:
    """Append-only audit event sink; it exposes snapshots, never its list."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._event_ids: set[str] = set()

    def append(self, event: AuditEvent) -> None:
        if event.event_id in self._event_ids:
            raise ValueError("audit event id already exists")
        if not event.reason.strip() or not event.before or not event.after:
            raise ValueError("audit event is incomplete")
        self._events.append(event)
        self._event_ids.add(event.event_id)

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)


@dataclass(frozen=True)
class AdminUserView:
    user_id: str
    email: str
    status: str
    tenant_id: str
    plan: str
    credit_balance: int


@dataclass(frozen=True)
class AdminOperationResult:
    action: str
    target_user_id: str
    before: Mapping[str, object]
    after: Mapping[str, object]
    audit_event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", _freeze(self.before))
        object.__setattr__(self, "after", _freeze(self.after))


class InMemoryEntitlements:
    """Test/local adapter for the provider-neutral entitlement port."""

    def __init__(self, plans: Mapping[str, str] | None = None) -> None:
        self.plans = dict(plans or {})
        self.transition_calls: list[tuple[str, str, str]] = []

    def current_plan(self, user_id: str) -> str:
        return self.plans.get(user_id, "free")

    def transition_plan(self, user_id: str, plan: str, *, reason: str) -> str:
        if plan not in {"free", "pro", "team", "enterprise"}:
            raise ValueError("unsupported plan")
        self.transition_calls.append((user_id, plan, reason))
        self.plans[user_id] = plan
        return plan


class InMemoryCreditLedger:
    """Test/local adapter for the typed credit-ledger port."""

    def __init__(self, balances: Mapping[str, int] | None = None) -> None:
        self.balances = dict(balances or {})
        self.adjustment_calls: list[tuple[str, int, str]] = []

    def current_balance(self, user_id: str) -> int:
        return self.balances.get(user_id, 0)

    def adjust_credits(self, user_id: str, amount: int, *, reason: str) -> int:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
            raise ValueError("credit adjustment must be a non-zero integer")
        self.adjustment_calls.append((user_id, amount, reason))
        self.balances[user_id] = self.current_balance(user_id) + amount
        return self.balances[user_id]


class AdminOperations:
    """Admin API application service; UI callers never mutate domain state."""

    def __init__(
        self,
        identity: TenantBoundary,
        entitlements: EntitlementPort,
        ledger: CreditLedgerPort,
        audit: AuditLog,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._identity = identity
        self._entitlements = entitlements
        self._ledger = ledger
        self._audit = audit
        self._clock = clock
        self._idempotent_results: dict[tuple[str, str], AdminOperationResult] = {}

    def _target(self, actor: RequestContext, tenant_id: str, target_user_id: str, permission: str) -> None:
        self._identity.require_admin(actor, tenant_id, permission)
        if not any(
            membership.user_id == target_user_id
            for membership in self._identity.memberships_for_tenant(tenant_id)
        ):
            raise AuthorizationDenied("target access denied")

    def _snapshot(self, tenant_id: str, user_id: str) -> dict[str, object]:
        user = self._identity.user(user_id)
        return {
            "tenant_id": tenant_id,
            "user_id": user.user_id,
            "status": user.status,
            "plan": self._entitlements.current_plan(user_id),
            "credit_balance": self._ledger.current_balance(user_id),
        }

    def _result(
        self,
        *,
        action: str,
        actor: RequestContext,
        tenant_id: str,
        target_user_id: str,
        reason: str,
        source: str,
        correlation_id: str,
        before: Mapping[str, object],
        after: Mapping[str, object],
        idempotency_key: str | None,
    ) -> AdminOperationResult:
        event = AuditEvent(
            event_id=f"audit-{uuid.uuid4().hex}",
            occurred_at=self._clock().astimezone(timezone.utc),
            actor_user_id=actor.user_id,
            actor_tenant_id=tenant_id,
            action=action,
            target_type="user",
            target_id=target_user_id,
            reason=reason,
            before=before,
            after=after,
            source=source,
            correlation_id=correlation_id,
        )
        self._audit.append(event)
        result = AdminOperationResult(action, target_user_id, before, after, event.event_id)
        if idempotency_key:
            self._idempotent_results[(action, idempotency_key)] = result
        return result

    def search_users(
        self,
        actor: RequestContext,
        tenant_id: str,
        *,
        query: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[AdminUserView, ...]:
        self._identity.require_admin(actor, tenant_id, "admin.users.read")
        if page < 1 or page_size < 1 or page_size > 100:
            raise ValueError("invalid pagination")
        needle = query.strip().lower()
        users = []
        for membership in self._identity.memberships_for_tenant(tenant_id):
            user = self._identity.user(membership.user_id)
            if needle and needle not in user.user_id.lower() and needle not in user.email.lower():
                continue
            users.append(
                AdminUserView(
                    user_id=user.user_id,
                    email=user.email,
                    status=user.status,
                    tenant_id=tenant_id,
                    plan=self._entitlements.current_plan(user.user_id),
                    credit_balance=self._ledger.current_balance(user.user_id),
                )
            )
        start = (page - 1) * page_size
        return tuple(users[start : start + page_size])

    def get_user(self, actor: RequestContext, tenant_id: str, target_user_id: str) -> AdminUserView:
        self._target(actor, tenant_id, target_user_id, "admin.users.read")
        user = self._identity.user(target_user_id)
        return AdminUserView(
            user_id=user.user_id,
            email=user.email,
            status=user.status,
            tenant_id=tenant_id,
            plan=self._entitlements.current_plan(target_user_id),
            credit_balance=self._ledger.current_balance(target_user_id),
        )

    def change_plan(
        self,
        actor: RequestContext,
        tenant_id: str,
        target_user_id: str,
        plan: str,
        *,
        reason: str,
        source: str = "admin-api",
        correlation_id: str = "unspecified",
        idempotency_key: str | None = None,
    ) -> AdminOperationResult:
        self._target(actor, tenant_id, target_user_id, "admin.plans.write")
        reason = _reason(reason)
        if idempotency_key and ("plan.change", idempotency_key) in self._idempotent_results:
            return self._idempotent_results[("plan.change", idempotency_key)]
        before = self._snapshot(tenant_id, target_user_id)
        self._entitlements.transition_plan(target_user_id, plan, reason=reason)
        after = self._snapshot(tenant_id, target_user_id)
        return self._result(
            action="plan.change",
            actor=actor,
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            reason=reason,
            source=source,
            correlation_id=correlation_id,
            before=before,
            after=after,
            idempotency_key=idempotency_key,
        )

    def adjust_credits(
        self,
        actor: RequestContext,
        tenant_id: str,
        target_user_id: str,
        amount: int,
        *,
        reason: str,
        source: str = "admin-api",
        correlation_id: str = "unspecified",
        idempotency_key: str | None = None,
    ) -> AdminOperationResult:
        self._target(actor, tenant_id, target_user_id, "admin.credits.write")
        reason = _reason(reason)
        if idempotency_key and ("credits.adjust", idempotency_key) in self._idempotent_results:
            return self._idempotent_results[("credits.adjust", idempotency_key)]
        before = self._snapshot(tenant_id, target_user_id)
        self._ledger.adjust_credits(target_user_id, amount, reason=reason)
        after = self._snapshot(tenant_id, target_user_id)
        return self._result(
            action="credits.adjust",
            actor=actor,
            tenant_id=tenant_id,
            target_user_id=target_user_id,
            reason=reason,
            source=source,
            correlation_id=correlation_id,
            before=before,
            after=after,
            idempotency_key=idempotency_key,
        )

