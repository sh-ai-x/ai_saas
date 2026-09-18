from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from services.billing.adapters.lemon_squeezy import LemonSqueezyAdapter
from services.billing.adapters.mock import MockPaymentAdapter
from services.billing.adapters.toss import TossPaymentsAdapter
from services.billing.errors import InvalidWebhook, ProviderConfigurationError
from services.billing.models import CreateOrder
from services.billing.registry import ProviderRegistry, build_registry, build_registry_from_environment
from services.billing.service import BillingService
from services.billing.store import SQLiteBillingStore
from services.billing.contract_check import run_contract_checks
from foundation.config import ConfigError, validate_profile


NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def payload(**overrides: object) -> bytes:
    value: dict[str, object] = {
        "event_id": "evt-1",
        "event_type": "payment.succeeded",
        "order_id": "order-1",
        "status": "DONE",
        "occurred_at": NOW.isoformat(),
        "amount_minor": 1200,
        "idempotency_key": "idem-evt-1",
        "test_mode": True,
    }
    value.update(overrides)
    return json.dumps(value, separators=(",", ":")).encode()


class BillingPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteBillingStore(":memory:")
        self.adapter = MockPaymentAdapter(webhook_secret="mock-secret")
        self.service = BillingService(
            store=self.store,
            providers=ProviderRegistry({"mock": self.adapter}),
            active_provider="mock",
            clock=lambda: NOW,
        )

    def tearDown(self) -> None:
        self.store.close()

    def test_mock_and_real_events_use_one_transactional_path(self) -> None:
        self.service.create_order(
            CreateOrder(
                order_id="order-1",
                tenant_id="tenant-1",
                account_id="account-1",
                plan_id="pro",
                amount_minor=1200,
                currency="USD",
                credit_grant=10,
                idempotency_key="order-idem-1",
            )
        )
        event = payload()
        signature = hmac.new(b"mock-secret", event, hashlib.sha256).hexdigest()
        first = self.service.receive_webhook(
            "mock", event, {"X-Signature": signature}
        )
        second = self.service.receive_webhook(
            "mock", event, {"X-Signature": signature}
        )

        self.assertTrue(first.applied)
        self.assertFalse(second.applied)
        self.assertEqual(self.store.order("order-1").status, "succeeded")
        self.assertEqual(self.store.entitlement("account-1").plan, "pro")
        self.assertEqual(self.store.balance("account-1"), 10)
        self.assertEqual(len(self.store.inbox()), 1)
        self.assertEqual(len(self.store.audit_events()), 1)

    def test_invalid_raw_event_never_enters_inbox(self) -> None:
        with self.assertRaises(InvalidWebhook):
            self.service.receive_webhook("mock", payload(), {"X-Signature": "bad"})
        self.assertEqual(self.store.inbox(), ())

    def test_event_amount_must_match_the_pending_order(self) -> None:
        self.service.create_order(
            CreateOrder(
                order_id="order-1",
                tenant_id="tenant-1",
                account_id="account-1",
                plan_id="pro",
                amount_minor=1200,
                currency="USD",
                credit_grant=10,
                idempotency_key="order-idem-1",
            )
        )
        body = payload(amount_minor=999)
        signature = hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()
        with self.assertRaises(ValueError):
            self.service.receive_webhook("mock", body, {"X-Signature": signature})
        self.assertEqual(self.store.inbox(), ())
        self.assertEqual(self.store.balance("account-1"), 0)

    def test_refund_reverses_entitlement_and_credits_atomically(self) -> None:
        self.service.create_order(
            CreateOrder(
                order_id="order-1",
                tenant_id="tenant-1",
                account_id="account-1",
                plan_id="pro",
                amount_minor=1200,
                currency="USD",
                credit_grant=10,
                idempotency_key="order-idem-1",
            )
        )
        for body in (payload(), payload(event_id="evt-refund", idempotency_key="idem-refund", status="REFUNDED")):
            signature = hmac.new(b"mock-secret", body, hashlib.sha256).hexdigest()
            self.service.receive_webhook("mock", body, {"X-Signature": signature})
        self.assertEqual(self.store.order("order-1").status, "refunded")
        self.assertEqual(self.store.entitlement("account-1").plan, "free")
        self.assertEqual(self.store.balance("account-1"), 0)
        self.assertEqual(len(self.store.audit_events()), 2)

    def test_pending_order_and_inbox_are_durable_across_store_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/billing.sqlite"
            first_store = SQLiteBillingStore(path)
            first_service = BillingService(
                store=first_store,
                providers=ProviderRegistry({"mock": self.adapter}),
                active_provider="mock",
                clock=lambda: NOW,
            )
            first_service.create_order(
                CreateOrder(
                    order_id="order-1",
                    tenant_id="tenant-1",
                    account_id="account-1",
                    plan_id="pro",
                    amount_minor=1200,
                    currency="USD",
                    credit_grant=10,
                    idempotency_key="order-idem-1",
                )
            )
            first_store.close()
            second_store = SQLiteBillingStore(path)
            self.assertEqual(second_store.order("order-1").status, "pending")
            self.assertEqual(second_store.inbox(), ())
            second_store.close()

    def test_concurrent_duplicate_delivery_grants_once(self) -> None:
        order = CreateOrder(
            order_id="order-1",
            tenant_id="tenant-1",
            account_id="account-1",
            plan_id="pro",
            amount_minor=1200,
            currency="USD",
            credit_grant=10,
            idempotency_key="order-idem-1",
        )
        self.service.create_order(order)
        event = payload()
        signature = hmac.new(b"mock-secret", event, hashlib.sha256).hexdigest()
        results: list[bool] = []

        def deliver() -> None:
            results.append(
                self.service.receive_webhook(
                    "mock", event, {"X-Signature": signature}
                ).applied
            )

        threads = [threading.Thread(target=deliver) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.store.balance("account-1"), 10)
        self.assertEqual(len(self.store.audit_events()), 1)

    def test_billing_integrity_contract_covers_req3_path(self) -> None:
        messages = run_contract_checks()
        self.assertTrue(any("REQ-3" in message for message in messages))


class AdapterContractTests(unittest.TestCase):
    def test_toss_signature_and_status_are_normalized(self) -> None:
        adapter = TossPaymentsAdapter(webhook_secret="toss-secret")
        body = payload(status="DONE", event_id="toss-event", idempotency_key="toss-idem")
        signature = hmac.new(b"toss-secret", body, hashlib.sha256).hexdigest()
        event = adapter.verify_and_normalize_event(body, {"X-Signature": signature})
        self.assertEqual(event.provider, "toss")
        self.assertEqual(event.status, "succeeded")

    def test_toss_malformed_official_signature_is_rejected_as_webhook_error(self) -> None:
        adapter = TossPaymentsAdapter(webhook_secret="toss-secret")
        with self.assertRaises(InvalidWebhook):
            adapter.verify_and_normalize_event(
                payload(),
                {
                    "tosspayments-webhook-signature": "v1:not-base64",
                    "tosspayments-webhook-transmission-time": "2026-09-18T00:00:00Z",
                },
            )

    def test_lemon_squeezy_uses_x_signature_and_json_api_shape(self) -> None:
        adapter = LemonSqueezyAdapter(webhook_secret="lemon-secret")
        value = {
            "meta": {"event_name": "subscription_created", "custom_data": {"order_id": "order-1"}},
            "data": {
                "id": "subscription-1",
                "attributes": {"status": "active", "created_at": NOW.isoformat()},
            },
        }
        body = json.dumps(value, separators=(",", ":")).encode()
        signature = hmac.new(b"lemon-secret", body, hashlib.sha256).hexdigest()
        event = adapter.verify_and_normalize_event(body, {"X-Signature": signature})
        self.assertEqual(event.provider, "lemon-squeezy")
        self.assertEqual(event.status, "succeeded")
        self.assertEqual(event.order_id, "order-1")

    def test_short_provider_identity_gets_a_stable_contract_safe_idempotency_key(self) -> None:
        adapter = LemonSqueezyAdapter(webhook_secret="lemon-secret")
        body = json.dumps(
            {
                "meta": {"event_name": "order_created", "custom_data": {"order_id": "order-1"}},
                "data": {"id": "1", "attributes": {"status": "paid"}},
            },
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(b"lemon-secret", body, hashlib.sha256).hexdigest()
        event = adapter.verify_and_normalize_event(body, {"X-Signature": signature})
        self.assertGreaterEqual(len(event.idempotency_key), 8)

    def test_registry_rejects_two_live_providers(self) -> None:
        with self.assertRaises(ProviderConfigurationError):
            build_registry(
                environment="production",
                selected_provider="toss",
                toss=object(),
                lemon_squeezy=object(),
            )

    def test_environment_can_enable_exactly_one_live_provider(self) -> None:
        values = {
            "APP_ENV": "staging",
            "DEPLOYMENT_PROFILE": "free-portfolio",
            "APP_BASE_URL": "https://app.example.test",
            "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
            "APP_SECRET_KEY": "x" * 64,
            "CONTRACT_VERSION": "v1",
            "PAYMENT_PROVIDER": "toss",
            "MOCK_PAYMENTS_ENABLED": "false",
            "WORKFLOW_PROVIDER": "local",
            "PAID_INFRASTRUCTURE": "false",
            "AWS_WORKER_ENABLED": "false",
            "TOSS_SECRET_KEY": "configured",
        }
        config = validate_profile(values)
        self.assertEqual(config.payment_provider, "toss")

        with self.assertRaises(ConfigError):
            validate_profile({**values, "PAYMENT_PROVIDER": "mock", "MOCK_PAYMENTS_ENABLED": "true", "APP_ENV": "production"})

        registry = build_registry_from_environment(values)
        self.assertEqual(set(registry), {"toss"})


if __name__ == "__main__":
    unittest.main()

