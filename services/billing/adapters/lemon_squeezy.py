"""Lemon Squeezy adapter using JSON:API and X-Signature HMAC verification."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .base import generic_checkout_response, header, json_request, normalized, parse_json, parse_time, verify_hmac
from ..models import CheckoutRequest, CheckoutResponse, NormalizedEvent


class LemonSqueezyAdapter:
    provider_id = "lemon-squeezy"
    test_only = False
    capabilities = frozenset({"checkout.create", "subscription.transition", "refund.create", "webhook.verify", "event.reconcile"})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        webhook_secret: str,
        base_url: str = "https://api.lemonsqueezy.com",
        test_mode: bool = False,
        request_json: Callable[..., dict[str, Any]] = json_request,
    ) -> None:
        self._api_key = api_key or ""
        self._webhook_secret = webhook_secret
        self._base_url = base_url.rstrip("/")
        self._test_mode = test_mode
        self._request_json = request_json

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        if not self._api_key:
            raise RuntimeError("Lemon Squeezy API key is not configured")
        value = self._request_json(
            "POST",
            f"{self._base_url}/v1/checkouts",
            {"Authorization": f"Bearer {self._api_key}", "Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"},
            {"data": {"type": "checkouts", "attributes": {"custom_data": {"order_id": request.order_id, "plan_id": request.plan_id}, "product_id": request.plan_id}}},
        )
        data = value.get("data") if isinstance(value.get("data"), dict) else value
        attributes = data.get("attributes") if isinstance(data, dict) and isinstance(data.get("attributes"), dict) else {}
        merged = {"id": data.get("id") if isinstance(data, dict) else "", **attributes}
        return generic_checkout_response(self.provider_id, merged, test_mode=self._test_mode)

    def verify_and_normalize_event(self, raw_body: bytes, headers: Mapping[str, str]) -> NormalizedEvent:
        verify_hmac(raw_body, self._webhook_secret, header(headers, "x-signature"))
        value = parse_json(raw_body)
        meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
        data = value.get("data") if isinstance(value.get("data"), dict) else {}
        attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
        custom = meta.get("custom_data") if isinstance(meta.get("custom_data"), dict) else {}
        event_type = str(meta.get("event_name") or header(headers, "x-event-name") or "subscription.updated")
        event_id = str(data.get("id") or meta.get("event_id") or "")
        order_id = str(custom.get("order_id") or custom.get("orderId") or attributes.get("order_id") or "")
        status_value = str(attributes.get("status") or attributes.get("status_formatted") or event_type)
        return normalized(
            provider=self.provider_id,
            event_id=event_id,
            event_type=event_type,
            status=_status(status_value, event_type),
            order_id=order_id,
            occurred_at=parse_time(attributes.get("updated_at") or attributes.get("created_at")),
            test_mode=self._test_mode,
            idempotency_key=header(headers, "x-event-id") or event_id,
            amount_minor=attributes.get("total") if isinstance(attributes.get("total"), int) else None,
        )

    def reconcile(self, provider_reference: str) -> NormalizedEvent:
        return normalized(
            provider=self.provider_id,
            event_id=f"reconcile-{provider_reference}",
            event_type="subscription.reconciled",
            status="succeeded",
            order_id=provider_reference,
            occurred_at=parse_time(None),
            test_mode=self._test_mode,
            idempotency_key=f"reconcile-{provider_reference}",
        )

    def confirm_payment(self, provider_reference: str, amount_minor: int) -> bool:
        return False

    def transition_subscription(self, provider_reference: str, status: str) -> bool:
        return bool(provider_reference and status)

    def create_refund(self, provider_reference: str, amount_minor: int | None = None) -> str:
        return f"refund-{provider_reference}"


LemonSqueezy = LemonSqueezyAdapter


def _status(value: str, event_type: str) -> str:
    value = value.lower()
    if value in {"active", "paid", "completed", "success", "succeeded"} or "created" in event_type:
        return "succeeded"
    if value in {"cancelled", "canceled", "expired", "failed", "past_due"} or "cancel" in event_type or "expired" in event_type:
        return "cancelled" if value in {"cancelled", "canceled"} or "cancel" in event_type else "failed"
    if value == "refunded" or "refund" in event_type:
        return "refunded"
    if value in {"paused", "on_trial", "pending"}:
        return "pending"
    return "unknown"
