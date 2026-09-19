from __future__ import annotations

import unittest

from foundation.config import ConfigError, validate_profile
from foundation.contract_check import check_contracts, validate_against_schema


def valid_free() -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "DEPLOYMENT_PROFILE": "free-portfolio",
        "APP_BASE_URL": "http://localhost:8080",
        "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
        "APP_SECRET_KEY": "x" * 64,
        "CONTRACT_VERSION": "v1",
        "PAYMENT_PROVIDER": "mock",
        "MOCK_PAYMENTS_ENABLED": "true",
        "WORKFLOW_PROVIDER": "local",
        "PAID_INFRASTRUCTURE": "false",
        "AWS_WORKER_ENABLED": "false",
    }


class ConfigurationTests(unittest.TestCase):
    def test_free_profile_accepts_safe_local_values(self) -> None:
        config = validate_profile(valid_free())
        self.assertEqual(config.deployment_profile, "free-portfolio")
        self.assertNotIn("APP_SECRET_KEY", config.values)

    def test_missing_secret_fails_closed(self) -> None:
        values = valid_free()
        values.pop("APP_SECRET_KEY")
        with self.assertRaises(ConfigError):
            validate_profile(values)

    def test_short_secret_fails_closed(self) -> None:
        values = valid_free()
        values["APP_SECRET_KEY"] = "x" * 31
        with self.assertRaises(ConfigError):
            validate_profile(values)

    def test_paid_resource_fails_closed(self) -> None:
        values = {**valid_free(), "REDIS_URL": "redis://paid"}
        with self.assertRaises(ConfigError):
            validate_profile(values)

    def test_explicit_worker_off_flag_is_safe(self) -> None:
        values = {**valid_free(), "AWS_ALWAYS_ON": "false"}
        validate_profile(values)


class ContractTests(unittest.TestCase):
    def test_contract_inventory_is_deterministic(self) -> None:
        self.assertEqual(
            check_contracts(),
            ["validated 17 versioned JSON contracts", "validated provider registry"],
        )

    def test_schema_rejects_unknown_fields(self) -> None:
        schema = {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string"}}}
        with self.assertRaises(AssertionError):
            validate_against_schema({"unexpected": True}, schema)


if __name__ == "__main__":
    unittest.main()
