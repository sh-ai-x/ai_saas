"""Executable billing contract checks used by the phase integrity gate."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from .adapters.lemon_squeezy import LemonSqueezyAdapter
from .adapters.mock import MockPaymentAdapter
from .adapters.toss import TossPaymentsAdapter
from .models import CreateOrder
from .registry import ProviderRegistry
from .service import BillingService
from .store import SQLiteBillingStore


def run_contract_checks() -> list[str]:
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    mock = MockPaymentAdapter(webhook_secret="integrity-secret")
    toss = TossPaymentsAdapter(webhook_secret="integrity-secret")
    lemon = LemonSqueezyAdapter(webhook_secret="integrity-secret")
    registry = ProviderRegistry({"mock": mock, "toss": toss, "lemon-squeezy": lemon})
    store = SQLiteBillingStore(":memory:")
    service = BillingService(store=store, providers=registry, active_provider="mock", clock=lambda: now)
    service.create_order(
        CreateOrder(
            order_id="integrity-order",
            tenant_id="integrity-tenant",
            account_id="integrity-account",
            plan_id="pro",
            amount_minor=1000,
            currency="USD",
            credit_grant=5,
            idempotency_key="integrity-order-key",
        )
    )
    body = json.dumps(
        {
            "event_id": "integrity-event",
            "event_type": "payment.succeeded",
            "order_id": "integrity-order",
            "status": "DONE",
            "occurred_at": now.isoformat(),
            "idempotency_key": "integrity-event-key",
            "test_mode": True,
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(b"integrity-secret", body, hashlib.sha256).hexdigest()
    first = service.receive_webhook("mock", body, {"X-Signature": signature})
    replay = service.receive_webhook("mock", body, {"X-Signature": signature})
    if not first.applied or replay.applied or store.balance("integrity-account") != 5:
        raise AssertionError("billing inbox idempotency or ledger effect failed")

    for adapter, event_body, headers in (
        (toss, body.replace(b"integrity-event", b"toss-event").replace(b"integrity-event-key", b"toss-event-key"), {"X-Signature": ""}),
        (lemon, json.dumps({"meta": {"event_name": "subscription_created", "custom_data": {"order_id": "integrity-order"}}, "data": {"id": "lemon-event", "attributes": {"status": "active"}}}, separators=(",", ":")).encode(), {"X-Signature": ""}),
    ):
        headers["X-Signature"] = hmac.new(b"integrity-secret", event_body, hashlib.sha256).hexdigest()
        normalized = adapter.verify_and_normalize_event(event_body, headers)
        if normalized.provider not in {"toss", "lemon-squeezy"} or normalized.status != "succeeded":
            raise AssertionError("real adapter did not produce the shared normalized event")
    store.close()
    return ["validated REQ-3 provider adapters share inbox, normalized-event, entitlement, ledger, and audit path"]
