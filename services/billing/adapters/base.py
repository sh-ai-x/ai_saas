"""Small standard-library helpers for HTTP and signed JSON adapters."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.request import Request, urlopen

from ..errors import InvalidWebhook
from ..models import CheckoutResponse, NormalizedEvent


def header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value.strip()
    return ""


def parse_json(raw_body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidWebhook("webhook body is not valid JSON") from exc
    if not isinstance(value, dict):
        raise InvalidWebhook("webhook body must be a JSON object")
    return value


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidWebhook("webhook occurred_at is invalid") from exc


def verify_hmac(raw_body: bytes, secret: str, supplied: str) -> None:
    if not secret or not supplied:
        raise InvalidWebhook("webhook signature is missing")
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied.lower()):
        raise InvalidWebhook("webhook signature is invalid")


def json_request(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=15) as response:
            data = response.read()
    except OSError as exc:
        raise RuntimeError("payment provider request failed") from exc
    value = parse_json(data)
    return value


def generic_checkout_response(provider: str, value: Mapping[str, Any], *, test_mode: bool) -> CheckoutResponse:
    reference = str(value.get("id") or value.get("paymentKey") or value.get("checkout_id") or "")
    url = str(value.get("checkout_url") or value.get("url") or value.get("hosted_url") or "")
    if not reference or not url:
        raise RuntimeError("provider checkout response is incomplete")
    return CheckoutResponse(provider, reference, url, test_mode)


def normalized(
    *,
    provider: str,
    event_id: str,
    event_type: str,
    status: str,
    order_id: str,
    occurred_at: datetime,
    test_mode: bool,
    idempotency_key: str,
    amount_minor: int | None = None,
    metadata: Mapping[str, str] | None = None,
) -> NormalizedEvent:
    if not event_id or not order_id:
        raise InvalidWebhook("webhook identity is incomplete")
    key = idempotency_key or event_id
    if len(key) < 8:
        key = f"{provider}:{key}"
    return NormalizedEvent(
        provider=provider,
        provider_event_id=event_id,
        event_type=event_type or "payment.updated",
        status=status,
        order_id=order_id,
        occurred_at=occurred_at,
        test_mode=test_mode,
        idempotency_key=key,
        amount_minor=amount_minor,
        metadata=metadata or {},
    )

