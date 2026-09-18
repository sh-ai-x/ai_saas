from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from foundation.config import validate_profile
from foundation.local_runtime import LocalRuntime
from foundation.server import LocalServer


def local_values(state_db: str) -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "DEPLOYMENT_PROFILE": "free-portfolio",
        "APP_BASE_URL": "http://127.0.0.1:0",
        "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
        "APP_SECRET_KEY": "local-test-secret-" + "x" * 48,
        "CONTRACT_VERSION": "v1",
        "PAYMENT_PROVIDER": "mock",
        "MOCK_PAYMENTS_ENABLED": "true",
        "WORKFLOW_PROVIDER": "local",
        "PAID_INFRASTRUCTURE": "false",
        "AWS_WORKER_ENABLED": "false",
        "LOCAL_STATE_DB": state_db,
        "LOCAL_INITIAL_CREDITS": "20",
    }


class LocalServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        values = local_values(str(Path(self.temp_dir.name) / "state.sqlite3"))
        config = validate_profile(values, "free-portfolio")
        self.runtime = LocalRuntime(config, values)
        self.server = LocalServer(("127.0.0.1", 0), self.runtime)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.runtime.close()
        self.temp_dir.cleanup()

    def request(self, method: str, path: str, payload: dict[str, object] | None = None, *, tenant: str = "demo-tenant") -> tuple[int, dict[str, object] | str]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json", "X-Tenant-Id": tenant},
            method=method,
        )
        try:
            with urlopen(request, timeout=3) as response:
                value = response.read().decode("utf-8")
                content_type = response.headers.get("Content-Type", "")
                return response.status, value if "text/event-stream" in content_type else json.loads(value)
        except HTTPError as exc:
            try:
                value = json.loads(exc.read().decode("utf-8"))
                return exc.code, value
            finally:
                exc.close()

    def test_local_vertical_slice_auth_run_sse_admin_and_payment(self) -> None:
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        google_status, google_start = self.request("GET", "/v1/auth/google/start")
        self.assertEqual(google_status, 200)
        callback_status, callback = self.request(
            "POST",
            "/v1/auth/google/callback",
            {"state": google_start["state"], "code": "local-code"},  # type: ignore[index]
        )
        self.assertEqual(callback_status, 200)
        self.assertEqual(callback["email"], "demo@example.test")  # type: ignore[index]

        run_status, run = self.request(
            "POST",
            "/v1/runs",
            {
                "contract_version": "v1",
                "tenant_id": "demo-tenant",
                "project_id": "demo-project",
                "idempotency_key": "local-test-run-001",
                "trace_id": "local-test-trace-001",
                "input": {"message": "hello"},
            },
        )
        self.assertEqual(run_status, 201)
        self.assertEqual(run["state"], "completed")  # type: ignore[index]
        run_id = run["run_id"]  # type: ignore[index]
        event_status, events = self.request("GET", f"/v1/runs/{run_id}/events")
        self.assertEqual(event_status, 200)
        self.assertIn("run.completed", events)  # type: ignore[operator]
        self.assertIn("Local echo: hello", events)  # type: ignore[operator]

        admin_status, admin_result = self.request(
            "POST",
            "/v1/admin/plan",
            {"target_user_id": "demo-member", "plan": "pro", "reason": "local test", "correlation_id": "corr-001"},
        )
        self.assertEqual(admin_status, 200)
        self.assertEqual(admin_result["after"]["plan"], "pro")  # type: ignore[index]
        credit_status, credit_result = self.request(
            "POST",
            "/v1/admin/credits",
            {"target_user_id": "demo-user", "amount": 3, "reason": "local credit grant", "correlation_id": "corr-credits-001"},
        )
        self.assertEqual(credit_status, 200)
        self.assertEqual(credit_result["after"]["credit_balance"], 22)  # type: ignore[index]

        order_status, order = self.request(
            "POST",
            "/v1/billing/orders",
            {"order_id": "local-order-001", "idempotency_key": "local-order-key-001", "amount_minor": 1000, "credit_grant": 5},
        )
        self.assertEqual(order_status, 201)
        order_read_status, order_read = self.request(
            "GET", f"/v1/billing/orders/{order['order_id']}", tenant="other-tenant"  # type: ignore[index]
        )
        self.assertEqual(order_read_status, 403)
        self.assertEqual(order_read["error"], "authorization_denied")  # type: ignore[index]
        payment_status, payment = self.request("POST", "/v1/billing/mock/complete", {"order_id": order["order_id"]})  # type: ignore[index]
        self.assertEqual(payment_status, 200)
        self.assertTrue(payment["applied"])  # type: ignore[index]
        duplicate_status, duplicate = self.request("POST", "/v1/billing/mock/complete", {"order_id": order["order_id"]})  # type: ignore[index]
        self.assertEqual(duplicate_status, 200)
        self.assertFalse(duplicate["applied"])  # type: ignore[index]

    def test_run_tenant_isolation_is_enforced_by_http_boundary(self) -> None:
        _, run = self.request(
            "POST",
            "/v1/runs",
            {
                "contract_version": "v1",
                "tenant_id": "demo-tenant",
                "project_id": "demo-project",
                "idempotency_key": "local-isolation-001",
                "trace_id": "local-isolation-trace-001",
                "input": {"message": "private"},
            },
        )
        status, response = self.request("GET", f"/v1/runs/{run['run_id']}", tenant="other-tenant")  # type: ignore[index]
        self.assertEqual(status, 403)
        self.assertEqual(response["error"], "tenant_access_denied")  # type: ignore[index]
        create_status, create_response = self.request(
            "POST",
            "/v1/runs",
            {
                "contract_version": "v1",
                "tenant_id": "demo-tenant",
                "project_id": "demo-project",
                "idempotency_key": "local-cross-tenant-create-001",
                "trace_id": "local-cross-tenant-create-trace-001",
                "input": {"message": "must fail"},
            },
            tenant="other-tenant",
        )
        self.assertEqual(create_status, 403)
        self.assertEqual(create_response["error"], "authorization_denied")  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
