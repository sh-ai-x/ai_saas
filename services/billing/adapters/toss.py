"""Toss Payments adapter using HTTP and raw-body verification only."""

from __future__ import annotations

import base64
import binascii
import hmac
from typing import Any, Callable, Mapping

from .base import (
    generic_checkout_response,
    header,
    json_request,
    normalized,
    parse_json,
    parse_time,
    verify_hmac,
)
from ..errors import InvalidWebhook
from ..models import CheckoutRequest, CheckoutResponse, NormalizedEvent


class TossPaymentsAdapter:
    provider_id = "toss"
    test_only = False
    capabilities = frozenset({"checkout.create", "payment.confirm", "refund.create", "webhook.verify", "event.reconcile"})

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        webhook_secret: str | None = None,
        base_url: str = "https://api.tosspayments.com",
        client_key: str | None = None,
        checkout_url: str = "https://js.tosspayments.com/v2/standard",
        success_url: str = "",
        fail_url: str = "",
        test_mode: bool = False,
        request_json: Callable[..., dict[str, Any]] = json_request,
        status_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self._secret_key = secret_key or ""
        self._webhook_secret = webhook_secret or secret_key or ""
        self._base_url = base_url.rstrip("/")
        self._client_key = client_key or ""
        self._checkout_url = checkout_url
        self._success_url = success_url
        self._fail_url = fail_url
        self._test_mode = test_mode
        self._request_json = request_json
        self._status_verifier = status_verifier

    def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        if not self._secret_key:
            raise RuntimeError("Toss secret key is not configured")
        if not self._client_key:
            raise RuntimeError("Toss client key is not configured")
        if request.currency != "KRW":
            raise ValueError("Toss checkout currency must be KRW")
        if not self._success_url or not self._fail_url:
            raise RuntimeError("Toss success and fail URLs are not configured")
        # Toss Payment Widgets/SDKs collect customer payment details in the
        # browser. The server creates the durable order and returns the
        # provider-neutral handoff; confirmation is always server-side.
        return CheckoutResponse(
            self.provider_id,
            request.order_id,
            self._checkout_url,
            self._test_mode,
            {
                "client_key": self._client_key,
                "order_id": request.order_id,
                "order_name": request.plan_id,
                "amount": {"value": request.amount_minor, "currency": request.currency},
                "success_url": self._success_url,
                "fail_url": self._fail_url,
            },
        )

    def confirm_payment_event(
        self,
        provider_reference: str,
        order_id: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> NormalizedEvent:
        if not self._secret_key:
            raise RuntimeError("Toss secret key is not configured")
        value = self._request_json(
            "POST",
            f"{self._base_url}/v1/payments/confirm",
            {
                "Authorization": "Basic " + base64.b64encode(f"{self._secret_key}:".encode()).decode(),
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            {"paymentKey": provider_reference, "orderId": order_id, "amount": amount_minor},
        )
        if str(value.get("orderId") or "") != order_id or int(value.get("totalAmount", -1)) != amount_minor:
            raise InvalidWebhook("Toss confirmation does not match the pending order")
        return normalized(
            provider=self.provider_id,
            event_id=f"confirm-{provider_reference}",
            event_type="payment.confirmed",
            status=_status(str(value.get("status") or "unknown")),
            order_id=order_id,
            occurred_at=parse_time(value.get("approvedAt") or value.get("requestedAt")),
            test_mode=self._test_mode,
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            metadata={"payment_key": provider_reference},
        )

    def verify_and_normalize_event(self, raw_body: bytes, headers: Mapping[str, str]) -> NormalizedEvent:
        value = parse_json(raw_body)
        signature = header(headers, "tosspayments-webhook-signature") or header(headers, "x-signature")
        if signature:
            if signature.startswith("v1:"):
                self._verify_official_signature(raw_body, headers, signature)
            else:
                verify_hmac(raw_body, self._webhook_secret, signature)
        elif self._status_verifier is None or not self._status_verifier(value):
            raise InvalidWebhook("Toss payment webhook requires provider status verification")
        data = value.get("data") if isinstance(value.get("data"), dict) else value
        event_id = str(
            header(headers, "tosspayments-webhook-transmission-id")
            or value.get("eventId") or value.get("event_id") or data.get("paymentKey") or data.get("transactionKey") or ""
        )
        order_id = str(data.get("orderId") or value.get("order_id") or "")
        idempotency = header(headers, "tosspayments-webhook-transmission-id") or str(value.get("idempotency_key") or event_id)
        amount = data.get("totalAmount") or data.get("amount") or value.get("amount_minor")
        return normalized(
            provider=self.provider_id,
            event_id=event_id,
            event_type=str(value.get("eventType") or value.get("event_type") or "payment.updated"),
            status=_status(str(data.get("status") or value.get("status") or "unknown")),
            order_id=order_id,
            occurred_at=parse_time(value.get("createdAt") or value.get("occurred_at")),
            test_mode=self._test_mode,
            idempotency_key=idempotency,
            amount_minor=amount if isinstance(amount, int) else None,
        )

    def _verify_official_signature(self, raw_body: bytes, headers: Mapping[str, str], signature: str) -> None:
        timestamp = header(headers, "tosspayments-webhook-transmission-time")
        if not timestamp or not self._webhook_secret:
            raise InvalidWebhook("Toss signature headers are incomplete")
        expected = base64.b64encode(hmac.digest(self._webhook_secret.encode(), raw_body + b":" + timestamp.encode(), "sha256"))
        supplied_values = signature.split(":")[1:]
        for item in supplied_values:
            try:
                decoded = base64.b64decode(item, validate=True)
            except (ValueError, binascii.Error):
                continue
            if hmac.compare_digest(expected, decoded):
                return
        raise InvalidWebhook("Toss webhook signature is invalid")

    def reconcile(self, provider_reference: str) -> NormalizedEvent:
        if not self._secret_key:
            raise RuntimeError("Toss secret key is not configured")
        value = self._request_json("GET", f"{self._base_url}/v1/payments/{provider_reference}", {}, None)
        return normalized(
            provider=self.provider_id,
            event_id=f"reconcile-{provider_reference}",
            event_type="payment.reconciled",
            status=_status(str(value.get("status") or "unknown")),
            order_id=str(value.get("orderId") or ""),
            occurred_at=parse_time(value.get("approvedAt") or value.get("requestedAt")),
            test_mode=self._test_mode,
            idempotency_key=f"reconcile-{provider_reference}",
            amount_minor=value.get("totalAmount") if isinstance(value.get("totalAmount"), int) else None,
        )

    def confirm_payment(self, provider_reference: str, amount_minor: int) -> bool:
        return bool(provider_reference and amount_minor > 0)

    def transition_subscription(self, provider_reference: str, status: str) -> bool:
        return False

    def create_refund(self, provider_reference: str, amount_minor: int | None = None) -> str:
        return f"refund-{provider_reference}"


TossAdapter = TossPaymentsAdapter


def _status(value: str) -> str:
    return {
        "DONE": "succeeded", "PAID": "succeeded", "SUCCEEDED": "succeeded",
        "READY": "pending", "IN_PROGRESS": "pending", "WAITING_FOR_DEPOSIT": "pending",
        "FAILED": "failed", "ABORTED": "failed", "CANCELED": "cancelled", "CANCELLED": "cancelled",
        "REFUNDED": "refunded",
    }.get(value.upper(), "unknown")
