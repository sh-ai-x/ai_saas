"""Billing application service: checkout creation and verified webhook intake."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Mapping

from .models import CheckoutRequest, CheckoutResponse, CreateOrder, ProcessingResult
from .registry import ProviderRegistry
from .store import SQLiteBillingStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BillingService:
    def __init__(
        self,
        *,
        store: SQLiteBillingStore,
        providers: ProviderRegistry,
        active_provider: str,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._providers = providers
        self._active_provider = active_provider
        self._clock = clock
        self._providers.require(active_provider, "checkout.create")

    def create_order(self, request: CreateOrder) -> CheckoutResponse:
        provider = self._providers.require(self._active_provider, "checkout.create")
        # The pending order is durable before any browser redirect is returned.
        self._store.create_pending_order(request, provider=self._active_provider)
        checkout = provider.create_checkout(
            CheckoutRequest(
                tenant_id=request.tenant_id,
                order_id=request.order_id,
                amount_minor=request.amount_minor,
                currency=request.currency,
                plan_id=request.plan_id,
                idempotency_key=request.idempotency_key,
            )
        )
        self._store.attach_checkout(request.order_id, self._active_provider, checkout.provider_reference)
        return checkout

    def receive_webhook(
        self, provider_id: str, raw_body: bytes, headers: Mapping[str, str]
    ) -> ProcessingResult:
        if provider_id != self._active_provider:
            raise ValueError("webhook provider is not enabled in this environment")
        provider = self._providers.require(provider_id, "webhook.verify")
        event = provider.verify_and_normalize_event(raw_body, headers)
        return self._store.process_event(event, raw_body, dict(headers))

    def confirm_payment(
        self,
        *,
        order_id: str,
        provider_reference: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> ProcessingResult:
        order = self._store.order(order_id)
        if order.provider != self._active_provider or order.amount_minor != amount_minor:
            raise ValueError("payment confirmation does not match the pending order")
        if order.status == "succeeded":
            return ProcessingResult(
                self._active_provider,
                f"confirm-{provider_reference}",
                False,
                "succeeded",
            )
        provider = self._providers.require(self._active_provider, "payment.confirm")
        confirmer = getattr(provider, "confirm_payment_event", None)
        if confirmer is None:
            raise ValueError("active payment provider requires webhook completion")
        event = confirmer(provider_reference, order_id, amount_minor, idempotency_key)
        return self._store.process_event(
            event,
            json.dumps(event.as_dict(), sort_keys=True).encode("utf-8"),
            {"x-confirmation-idempotency-key": idempotency_key},
        )
