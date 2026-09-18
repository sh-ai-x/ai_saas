"""Billing application service: checkout creation and verified webhook intake."""

from __future__ import annotations

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

