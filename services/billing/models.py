"""Provider-neutral billing value objects and normalized statuses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping


STATUSES = frozenset({"pending", "succeeded", "failed", "cancelled", "refunded", "unknown"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class CreateOrder:
    order_id: str
    tenant_id: str
    account_id: str
    plan_id: str
    amount_minor: int
    currency: str
    credit_grant: int
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in ("order_id", "tenant_id", "account_id", "plan_id", "currency", "idempotency_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool) or self.amount_minor <= 0:
            raise ValueError("amount_minor must be a positive integer")
        if not isinstance(self.credit_grant, int) or isinstance(self.credit_grant, bool) or self.credit_grant < 0:
            raise ValueError("credit_grant must be a non-negative integer")
        if len(self.idempotency_key) < 8:
            raise ValueError("idempotency_key must be at least 8 characters")
        object.__setattr__(self, "currency", self.currency.upper())


@dataclass(frozen=True)
class CheckoutRequest:
    tenant_id: str
    order_id: str
    amount_minor: int
    currency: str
    plan_id: str
    idempotency_key: str


@dataclass(frozen=True)
class CheckoutResponse:
    provider: str
    provider_reference: str
    checkout_url: str
    test_mode: bool


@dataclass(frozen=True)
class NormalizedEvent:
    provider: str
    provider_event_id: str
    event_type: str
    status: str
    order_id: str
    occurred_at: datetime
    test_mode: bool
    idempotency_key: str
    amount_minor: int | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unsupported normalized status: {self.status}")
        if not self.provider_event_id or not self.order_id or len(self.idempotency_key) < 8:
            raise ValueError("normalized event identity is incomplete")
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "provider_event_id": self.provider_event_id,
            "event_type": self.event_type,
            "status": self.status,
            "order_id": self.order_id,
            "occurred_at": self.occurred_at.isoformat(),
            "test_mode": self.test_mode,
            "idempotency_key": self.idempotency_key,
            "amount_minor": self.amount_minor,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Order:
    order_id: str
    tenant_id: str
    account_id: str
    plan_id: str
    amount_minor: int
    currency: str
    credit_grant: int
    idempotency_key: str
    status: str
    provider: str | None
    provider_reference: str | None


@dataclass(frozen=True)
class Entitlement:
    account_id: str
    plan: str
    version: int


@dataclass(frozen=True)
class InboxRecord:
    provider: str
    provider_event_id: str
    idempotency_key: str
    status: str
    applied: bool


@dataclass(frozen=True)
class AuditRecord:
    event_id: str
    action: str
    target_id: str
    before: Mapping[str, object]
    after: Mapping[str, object]


@dataclass(frozen=True)
class ProcessingResult:
    provider: str
    provider_event_id: str
    applied: bool
    status: str

