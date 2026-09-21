from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SANDBOX_COMPOSE = ROOT / "docker/prod/compose.toss-sandbox.yaml"


class TossSandboxComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = SANDBOX_COMPOSE.read_text(encoding="utf-8")

    def test_declares_a_separate_port_set_for_every_runtime_service(self) -> None:
        self.assertIn('"${TOSS_POSTGRES_PORT:-55433}:5433"', self.compose)
        self.assertIn('"${TOSS_FOUNDATION_PORT:-18081}:8081"', self.compose)
        self.assertIn('"${TOSS_WEB_PORT:-3001}:3001"', self.compose)
        self.assertIn('"postgres", "-p", "5433"', self.compose)
        self.assertIn('"--port", "8081"', self.compose)
        self.assertIn('PORT: "3001"', self.compose)

    def test_rewires_internal_database_and_foundation_urls(self) -> None:
        self.assertIn("postgresql://foundation@postgres:5433/foundation", self.compose)
        self.assertIn("FOUNDATION_API_URL: http://foundation:8081", self.compose)
        self.assertIn("pg_isready -U foundation -d foundation -p 5433", self.compose)
        self.assertIn("127.0.0.1:8081/healthz", self.compose)
        self.assertIn("127.0.0.1:3001", self.compose)

    def test_defaults_to_toss_sandbox_without_enabling_mock_payments(self) -> None:
        self.assertIn("PAYMENT_PROVIDER: toss", self.compose)
        self.assertGreaterEqual(self.compose.count("PAYMENT_PROVIDER: toss"), 2)
        self.assertIn("MOCK_PAYMENTS_ENABLED: \"false\"", self.compose)
        self.assertIn("PAYMENT_SANDBOX: \"true\"", self.compose)
        self.assertIn("TOSS_CLIENT_KEY: ${TOSS_CLIENT_KEY:?set TOSS_CLIENT_KEY", self.compose)
        self.assertIn("TOSS_SECRET_KEY: ${TOSS_SECRET_KEY:?set TOSS_SECRET_KEY", self.compose)


if __name__ == "__main__":
    unittest.main()
