from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.billing import BillingService, CreateOrder, SQLiteBillingStore
from services.billing.adapters.toss import TossPaymentsAdapter
from services.billing.registry import build_registry


class PaymentSandboxApiTests(unittest.TestCase):
    def test_toss_confirmation_uses_pending_order_and_applies_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def request_json(method, url, headers, payload):
                calls.append((method, url, headers, payload))
                return {"orderId": "sandbox-order", "totalAmount": 1000, "status": "DONE", "approvedAt": "2026-01-01T00:00:00Z"}

            adapter = TossPaymentsAdapter(
                secret_key="test_secret",
                webhook_secret="webhook_secret",
                test_mode=True,
                request_json=request_json,
            )
            registry = build_registry(environment="staging", selected_provider="toss", toss=adapter)
            store = SQLiteBillingStore(str(Path(directory) / "billing.sqlite3"))
            service = BillingService(store=store, providers=registry, active_provider="toss")
            service.create_order(
                CreateOrder("sandbox-order", "tenant", "account", "pro", 1000, "USD", 10, "sandbox-key-001")
            )
            result = service.confirm_payment(
                order_id="sandbox-order",
                provider_reference="payment-key",
                amount_minor=1000,
                idempotency_key="confirm-key-001",
            )
            duplicate = service.confirm_payment(
                order_id="sandbox-order",
                provider_reference="payment-key",
                amount_minor=1000,
                idempotency_key="confirm-key-001",
            )
            self.assertTrue(result.applied)
            self.assertFalse(duplicate.applied)
            self.assertEqual(store.balance("account"), 10)
            self.assertEqual(calls[0][1].endswith("/v1/payments/confirm"), True)
            store.close()

    def test_toss_confirmation_rejects_wrong_amount(self) -> None:
        adapter = TossPaymentsAdapter(secret_key="test_secret", webhook_secret="webhook_secret", test_mode=True)
        registry = build_registry(environment="staging", selected_provider="toss", toss=adapter)
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteBillingStore(str(Path(directory) / "billing.sqlite3"))
            service = BillingService(store=store, providers=registry, active_provider="toss")
            service.create_order(CreateOrder("order-amount", "tenant", "account", "pro", 1000, "USD", 10, "amount-key-001"))
            with self.assertRaises(ValueError):
                service.confirm_payment(order_id="order-amount", provider_reference="payment", amount_minor=999, idempotency_key="confirm-amount-001")
            store.close()


if __name__ == "__main__":
    unittest.main()
