"""Capability ports shared by every payment adapter and the billing domain."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from .models import CheckoutRequest, CheckoutResponse, NormalizedEvent


class CheckoutPort(Protocol):
    def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        ...


class PaymentConfirmationPort(Protocol):
    def confirm_payment(self, provider_reference: str, amount_minor: int) -> bool:
        ...


class SubscriptionPort(Protocol):
    def transition_subscription(self, provider_reference: str, status: str) -> bool:
        ...


class RefundPort(Protocol):
    def create_refund(self, provider_reference: str, amount_minor: int | None = None) -> str:
        ...


class WebhookVerificationPort(Protocol):
    def verify_and_normalize_event(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> NormalizedEvent:
        ...


class ReconciliationPort(Protocol):
    def reconcile(self, provider_reference: str) -> NormalizedEvent:
        ...


class PaymentProvider(
    CheckoutPort,
    PaymentConfirmationPort,
    SubscriptionPort,
    RefundPort,
    WebhookVerificationPort,
    ReconciliationPort,
    Protocol,
):
    provider_id: str
    test_only: bool
    capabilities: frozenset[str]


class EntitlementPort(Protocol):
    def set_plan(self, account_id: str, plan: str, *, reason: str) -> int:
        ...


class CreditLedgerPort(Protocol):
    def append(self, account_id: str, amount: int, *, idempotency_key: str, reason: str) -> int:
        ...


class AuditPort(Protocol):
    def append(self, action: str, target_id: str, before: Mapping[str, object], after: Mapping[str, object]) -> None:
        ...


EventVerifier = Callable[[bytes, Mapping[str, str]], NormalizedEvent]
