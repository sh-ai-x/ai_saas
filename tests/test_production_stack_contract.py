from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROD_COMPOSE = ROOT / "docker/prod/compose.yaml"
LOCAL_COMPOSE = ROOT / "docker/local/compose.yaml"


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

    def test_docker_local_uses_isolated_host_ports_without_changing_internal_ports(self) -> None:
        compose = PROD_COMPOSE.read_text(encoding="utf-8")
        postgres = service_block(compose, "postgres", "foundation")
        foundation = service_block(compose, "foundation", "web-migrate")
        web = service_block(compose, "web")

        self.assertIn('"${POSTGRES_PORT:-55433}:5432"', postgres)
        self.assertIn('"${FOUNDATION_PORT:-8180}:8080"', foundation)
        self.assertIn('"${WEB_PORT:-3100}:3000"', web)
        self.assertIn("postgresql://foundation@postgres:5432/foundation", compose)
        self.assertIn("APP_BASE_URL: ${FOUNDATION_PUBLIC_URL:-http://localhost:8180}", foundation)
        self.assertIn("FOUNDATION_API_URL: http://foundation:8080", web)
        self.assertIn("APP_BASE_URL: ${WEB_PUBLIC_URL:-http://localhost:3100}", web)
        self.assertIn("BETTER_AUTH_URL: ${BETTER_AUTH_URL:-http://localhost:3100}", web)

    def test_docker_env_example_matches_isolated_public_defaults(self) -> None:
        env_example = (ROOT / ".env.docker.example").read_text(encoding="utf-8")

        for expected in (
            "POSTGRES_PORT=55433",
            "FOUNDATION_PORT=8180",
            "WEB_PORT=3100",
            "FOUNDATION_PUBLIC_URL=http://localhost:8180",
            "WEB_PUBLIC_URL=http://localhost:3100",
            "BETTER_AUTH_URL=http://localhost:3100",
        ):
            self.assertIn(expected, env_example)

    def test_docker_local_script_promotes_legacy_defaults_but_keeps_explicit_ports(self) -> None:
        script = (ROOT / "scripts/docker-local.sh").read_text(encoding="utf-8")
        self.assertIn("use_isolated_host_port POSTGRES_PORT 5432 55433", script)
        self.assertIn("use_isolated_host_port FOUNDATION_PORT 8080 8180", script)
        self.assertIn("use_isolated_host_port WEB_PORT 3000 3100", script)
        self.assertIn("if [[ -z \"$shell_value\"", script)
        self.assertIn('compose_project="${COMPOSE_PROJECT_NAME:-ai-saas-proposal-verified-change}"', script)

    def test_docker_local_uses_the_lightweight_development_web_target(self) -> None:
        compose = LOCAL_COMPOSE.read_text(encoding="utf-8")
        dockerfile = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
        script = (ROOT / "scripts/docker-local.sh").read_text(encoding="utf-8")

        self.assertIn("target: development", compose)
        self.assertIn('next", "dev", "--hostname", "0.0.0.0", "--port", "3000"', compose)
        self.assertIn("FROM deps AS development", dockerfile)
        self.assertIn("docker/local/compose.yaml", script)


if __name__ == "__main__":
    unittest.main()
