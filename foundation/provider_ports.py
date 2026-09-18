"""Provider-neutral capability ports used by the billing boundary.

There are no provider SDK imports in this module. Toss, Lemon Squeezy, and the
non-production mock provider implement these application-owned ports in the
metering-billing adapter package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence

CONTRACT_VERSION = "v1"


@dataclass(frozen=True)
class CheckoutRequest:
    tenant_id: str
    order_id: str
    amount: Decimal
    currency: str
    plan_id: str
    idempotency_key: str


@dataclass(frozen=True)
class CheckoutResponse:
    provider: str
    provider_reference: str
    checkout_url: str
    test_mode: bool
    contract_version: str = CONTRACT_VERSION


@dataclass(frozen=True)
class NormalizedProviderEvent:
    provider: str
    provider_event_id: str
    event_type: str
    status: str
    order_id: str
    occurred_at: datetime
    test_mode: bool
    idempotency_key: str
    amount_minor: int | None = None
    metadata: Mapping[str, str] | None = None
    contract_version: str = CONTRACT_VERSION


class PaymentProvider(Protocol):
    """Application-owned port; domain code depends only on this interface."""

    provider_id: str
    test_only: bool

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        ...

    def verify_and_normalize_event(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> NormalizedProviderEvent:
        ...

    def reconcile(self, provider_reference: str) -> NormalizedProviderEvent:
        ...


PROVIDER_CAPABILITIES: Mapping[str, Sequence[str]] = {
    "mock": (
        "checkout.create",
        "payment.confirm",
        "subscription.transition",
        "refund.create",
        "webhook.verify",
        "event.reconcile",
    ),
    "toss": (
        "checkout.create",
        "payment.confirm",
        "refund.create",
        "webhook.verify",
        "event.reconcile",
    ),
    "lemon-squeezy": (
        "checkout.create",
        "subscription.transition",
        "refund.create",
        "webhook.verify",
        "event.reconcile",
    ),
}
