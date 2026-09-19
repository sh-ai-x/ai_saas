from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_COMPOSE = ROOT / "docker/prod/compose.yaml"


def service_block(compose: str, service: str, next_service: str | None = None) -> str:
    """Return one Compose service block without requiring a YAML dependency."""
    start = compose.index(f"  {service}:")
    end = len(compose)
    if next_service is not None:
        end = compose.index(f"  {next_service}:", start + 1)
    return compose[start:end]


class ProductionDockerContractTests(unittest.TestCase):
    def test_uv_cache_has_a_non_root_safe_default_in_both_images(self) -> None:
        for relative_path in ("docker/prod/foundation.Dockerfile", "docker/dev/Dockerfile"):
            content = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertRegex(content, r"(?m)^\s*UV_CACHE_DIR=/tmp/uv-cache \\\s*$")
            self.assertIn("USER app", content)
            self.assertRegex(content, r"chown -R app:app .*\$UV_CACHE_DIR")

    def test_production_compose_repeats_uv_cache_runtime_contract(self) -> None:
        compose = PROD_COMPOSE.read_text(encoding="utf-8")
        foundation = service_block(compose, "foundation", "web-migrate")
        self.assertIn("UV_CACHE_DIR: /tmp/uv-cache", foundation)
        self.assertIn("condition: service_healthy", foundation)

    def test_database_contract_is_passwordless_and_health_checked(self) -> None:
        compose = PROD_COMPOSE.read_text(encoding="utf-8")
        postgres = service_block(compose, "postgres", "foundation")
        foundation = service_block(compose, "foundation", "web-migrate")
        web_migrate = service_block(compose, "web-migrate", "web")
        web = service_block(compose, "web")

        self.assertIn("POSTGRES_HOST_AUTH_METHOD: trust", postgres)
        self.assertNotIn("POSTGRES_PASSWORD", postgres)
        self.assertIn("postgresql://foundation@postgres:5432/foundation", foundation)
        self.assertIn("postgresql://foundation@postgres:5432/foundation", web_migrate)
        self.assertIn("postgresql://foundation@postgres:5432/foundation", web)
        self.assertRegex(postgres, r"pg_isready -U foundation -d foundation")

    def test_auth_contract_passes_only_runtime_values_to_web(self) -> None:
        compose = PROD_COMPOSE.read_text(encoding="utf-8")
        web = service_block(compose, "web")

        for variable in (
            "BETTER_AUTH_URL",
            "BETTER_AUTH_SECRET",
            "NEXT_PUBLIC_GOOGLE_AUTH_ENABLED",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
        ):
            self.assertRegex(web, rf"(?m)^\s+{re.escape(variable)}:")
        self.assertNotRegex(web, r"NEXT_PUBLIC_GOOGLE_CLIENT_(ID|SECRET)")
        self.assertIn("APP_SECRET_KEY: ${APP_SECRET_KEY:?set APP_SECRET_KEY", compose)


if __name__ == "__main__":
    unittest.main()
