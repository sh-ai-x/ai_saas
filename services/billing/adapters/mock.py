"""Deterministic, test-only payment adapter."""

from __future__ import annotations

import uuid
from typing import Mapping

from .base import header, parse_json, parse_time, normalized, verify_hmac
from ..models import CheckoutRequest, CheckoutResponse, NormalizedEvent


class MockPaymentAdapter:
    provider_id = "mock"
    test_only = True
    capabilities = frozenset({
        "checkout.create", "payment.confirm", "subscription.transition",
        "refund.create", "webhook.verify", "event.reconcile",
    })

    def __init__(self, *, webhook_secret: str = "mock-secret") -> None:
        self._webhook_secret = webhook_secret

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        return CheckoutResponse(
            self.provider_id,
            f"mock-payment-{uuid.uuid4().hex}",
            f"https://mock.invalid/checkout/{request.order_id}",
            True,
        )

    def verify_and_normalize_event(self, raw_body: bytes, headers: Mapping[str, str]) -> NormalizedEvent:
        verify_hmac(raw_body, self._webhook_secret, header(headers, "x-signature"))
        value = parse_json(raw_body)
        return normalized(
            provider=self.provider_id,
            event_id=str(value.get("event_id") or value.get("id") or ""),
            event_type=str(value.get("event_type") or "payment.updated"),
            status=_status(str(value.get("status") or "unknown")),
            order_id=str(value.get("order_id") or ""),
            occurred_at=parse_time(value.get("occurred_at")),
            test_mode=bool(value.get("test_mode", True)),
            idempotency_key=str(value.get("idempotency_key") or value.get("event_id") or ""),
            amount_minor=value.get("amount_minor") if isinstance(value.get("amount_minor"), int) else None,
        )

    def reconcile(self, provider_reference: str) -> NormalizedEvent:
        return normalized(
            provider=self.provider_id,
            event_id=f"reconcile-{provider_reference}",
            event_type="payment.reconciled",
            status="succeeded",
            order_id=provider_reference,
            occurred_at=parse_time(None),
            test_mode=True,
            idempotency_key=f"reconcile-{provider_reference}",
        )

    def confirm_payment(self, provider_reference: str, amount_minor: int) -> bool:
        return bool(provider_reference and amount_minor > 0)

    def transition_subscription(self, provider_reference: str, status: str) -> bool:
        return bool(provider_reference and status)

    def create_refund(self, provider_reference: str, amount_minor: int | None = None) -> str:
        return f"mock-refund-{provider_reference}"


MockAdapter = MockPaymentAdapter


def _status(value: str) -> str:
    return {
        "DONE": "succeeded", "PAID": "succeeded", "SUCCEEDED": "succeeded",
        "READY": "pending", "PENDING": "pending", "IN_PROGRESS": "pending",
        "FAILED": "failed", "ABORTED": "failed", "CANCELED": "cancelled", "CANCELLED": "cancelled",
        "REFUNDED": "refunded",
    }.get(value.upper(), "unknown")

