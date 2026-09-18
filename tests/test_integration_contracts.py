from __future__ import annotations

import unittest

from foundation.config import ConfigError, validate_profile


def base_values() -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "DEPLOYMENT_PROFILE": "free-portfolio",
        "APP_BASE_URL": "http://127.0.0.1:3000",
        "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
        "APP_SECRET_KEY": "x" * 64,
        "CONTRACT_VERSION": "v1",
        "PAYMENT_PROVIDER": "mock",
        "MOCK_PAYMENTS_ENABLED": "true",
        "PAYMENT_SANDBOX": "true",
        "AUTH_PROVIDER": "local-mock",
        "AGENT_PROVIDER": "local",
        "AGENT_MODEL": "local-echo",
        "WORKFLOW_PROVIDER": "local",
        "PAID_INFRASTRUCTURE": "false",
        "AWS_WORKER_ENABLED": "false",
    }


class IntegrationConfigurationTests(unittest.TestCase):
    def test_google_profile_accepts_server_only_credentials(self) -> None:
        values = {
            **base_values(),
            "AUTH_PROVIDER": "google",
            "GOOGLE_CLIENT_ID": "client.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "secret",
            "GOOGLE_REDIRECT_URI": "http://127.0.0.1:3000/auth/callback",
        }
        config = validate_profile(values, "free-portfolio")
        self.assertTrue(config.google_configured)
        self.assertNotIn("GOOGLE_CLIENT_SECRET", config.values)

    def test_staging_live_payment_requires_sandbox(self) -> None:
        values = {
            **base_values(),
            "PAYMENT_PROVIDER": "toss",
            "MOCK_PAYMENTS_ENABLED": "false",
            "PAYMENT_SANDBOX": "false",
            "TOSS_SECRET_KEY": "test_secret",
        }
        with self.assertRaises(ConfigError):
            validate_profile(values, "free-portfolio")

    def test_non_local_agent_requires_key_and_bounds(self) -> None:
        values = {**base_values(), "AGENT_PROVIDER": "openai", "AGENT_MODEL": "gpt-4o-mini"}
        with self.assertRaises(ConfigError):
            validate_profile(values, "free-portfolio")
        values["AGENT_API_KEY"] = "runtime-secret"
        values["AGENT_MAX_OUTPUT_TOKENS"] = "4097"
        with self.assertRaises(ConfigError):
            validate_profile(values, "free-portfolio")

    def test_two_live_payment_providers_fail_closed(self) -> None:
        values = {
            **base_values(),
            "PAYMENT_PROVIDER": "toss",
            "MOCK_PAYMENTS_ENABLED": "false",
            "TOSS_SECRET_KEY": "test_secret",
            "LEMONSQUEEZY_API_KEY": "test_key",
        }
        with self.assertRaises(ConfigError):
            validate_profile(values, "free-portfolio")


if __name__ == "__main__":
    unittest.main()
