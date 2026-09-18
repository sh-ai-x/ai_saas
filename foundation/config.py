"""Fail-closed environment profile loading and validation.

The foundation intentionally uses only the standard library in this step.
Framework-specific application and worker configuration must preserve these
profile invariants and must not make paid infrastructure an implicit default.
"""

from __future__ import annotations

import argparse
import math
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

PROFILES = ("free-portfolio", "aws-worker")
PAYMENT_PROVIDERS = frozenset({"mock", "toss", "lemon-squeezy"})
LIVE_PAYMENT_PROVIDERS = frozenset({"toss", "lemon-squeezy"})
AUTH_PROVIDERS = frozenset({"local-mock", "google"})
AGENT_PROVIDERS = frozenset({"local", "openai", "anthropic", "gemini"})
CONTRACT_VERSION = "v1"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_PLACEHOLDER_SECRETS = {
    "change-me",
    "replace-me",
    "replace-with-a-random-value",
    "generate-with-openssl",
    "your-secret",
}

COMMON_REQUIRED = (
    "APP_ENV",
    "APP_BASE_URL",
    "DATABASE_URL",
    "APP_SECRET_KEY",
    "CONTRACT_VERSION",
    "PAYMENT_PROVIDER",
    "MOCK_PAYMENTS_ENABLED",
    "PAID_INFRASTRUCTURE",
    "WORKFLOW_PROVIDER",
)

# These names are intentionally explicit.  They are the resources this
# foundation is forbidden to add implicitly; a non-empty value is rejected in
# both profiles rather than being silently ignored.
FORBIDDEN_PAID_KEYS = (
    "ALB_ARN",
    "NAT_GATEWAY_ID",
    "REDIS_URL",
)


class ConfigError(ValueError):
    """Raised when configuration cannot safely describe a deployment profile."""


@dataclass(frozen=True)
class FoundationConfig:
    """Validated, non-secret configuration consumed by the local server."""

    app_env: str
    app_base_url: str
    database_url: str
    contract_version: str
    deployment_profile: str
    payment_provider: str
    mock_payments_enabled: bool
    payment_sandbox: bool
    auth_provider: str
    google_configured: bool
    agent_provider: str
    agent_model: str
    agent_max_output_tokens: int
    agent_timeout_seconds: int
    agent_base_url: str | None
    workflow_provider: str
    aws_worker_enabled: bool
    quota_max_runs: int
    quota_max_units: int
    quota_period_seconds: int
    otel_enabled: bool
    otel_sample_rate: float
    values: Mapping[str, str]

    @property
    def live_payment_provider(self) -> str | None:
        return None if self.payment_provider == "mock" else self.payment_provider


def load_env_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """Read a small dotenv file without evaluating shell syntax.

    Only ``KEY=value`` lines, comments, and shell-style quoted values are
    accepted.  Variable expansion and command substitution are deliberately
    unsupported so a configuration file cannot execute code.
    """

    env_path = Path(path)
    if not env_path.is_file():
        raise ConfigError(f"environment file does not exist: {env_path}")

    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"invalid environment assignment at {env_path}:{line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or not key[0].isalpha():
            raise ConfigError(f"invalid environment key at {env_path}:{line_number}")
        try:
            parsed = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as exc:
            raise ConfigError(f"invalid environment value at {env_path}:{line_number}") from exc
        result[key] = " ".join(parsed) if parsed else ""
    return result


def _bool(values: Mapping[str, str], key: str) -> bool:
    raw = values.get(key, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"{key} must be one of true/false")


def _require(values: Mapping[str, str], key: str, errors: list[str]) -> str:
    value = values.get(key, "").strip()
    if not value:
        errors.append(f"missing required setting: {key}")
    return value


def _bounded_int(values: Mapping[str, str], key: str, default: int, errors: list[str], *, maximum: int) -> int:
    raw = values.get(key, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        errors.append(f"{key} must be a positive integer")
        return default
    if parsed <= 0 or parsed > maximum:
        errors.append(f"{key} must be between 1 and {maximum}")
        return default
    return parsed


def _bounded_float(values: Mapping[str, str], key: str, default: float, errors: list[str]) -> float:
    raw = values.get(key, str(default)).strip()
    try:
        parsed = float(raw)
    except ValueError:
        errors.append(f"{key} must be between 0 and 1")
        return default
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        errors.append(f"{key} must be between 0 and 1")
        return default
    return parsed


def _reject_paid_or_unsafe(values: Mapping[str, str], errors: list[str]) -> None:
    for key in FORBIDDEN_PAID_KEYS:
        if values.get(key, "").strip():
            errors.append(f"forbidden paid/always-on setting is present: {key}")

    for key in ("VERCEL_PLAN", "CLOUDFLARE_PLAN"):
        plan = values.get(key, "").strip().lower()
        if plan and plan not in {"free", "hobby"}:
            errors.append(f"paid plan is not allowed by the foundation profile: {key}")

    for key in ("PAID_INFRASTRUCTURE", "AWS_ALWAYS_ON"):
        raw = values.get(key, "").strip().lower()
        if raw in _TRUE:
            errors.append(f"{key}=true is not allowed by the foundation profile")


def validate_profile(
    values: Mapping[str, str], profile: str | None = None
) -> FoundationConfig:
    """Validate one profile and return a safe configuration view.

    Validation collects all failures and reports only setting names, never
    values.  Unknown settings are tolerated for forward compatibility, while
    known paid-resource settings are rejected explicitly.
    """

    selected = (profile or values.get("DEPLOYMENT_PROFILE", "")).strip()
    errors: list[str] = []
    if selected not in PROFILES:
        errors.append(f"DEPLOYMENT_PROFILE must be one of: {', '.join(PROFILES)}")

    required = {key: _require(values, key, errors) for key in COMMON_REQUIRED}
    if selected in PROFILES:
        declared = values.get("DEPLOYMENT_PROFILE", "").strip()
        if declared and declared != selected:
            errors.append("DEPLOYMENT_PROFILE does not match the requested profile")

    if required["CONTRACT_VERSION"] != CONTRACT_VERSION:
        errors.append(f"CONTRACT_VERSION must be {CONTRACT_VERSION}")

    app_env = required["APP_ENV"].lower()
    if app_env not in {"local", "test", "staging", "production"}:
        errors.append("APP_ENV must be local, test, staging, or production")

    parsed_url = urlparse(required["APP_BASE_URL"])
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        errors.append("APP_BASE_URL must be an absolute http(s) URL")

    if not required["DATABASE_URL"].startswith(("postgresql://", "postgres://")):
        errors.append("DATABASE_URL must be a PostgreSQL URL")

    secret = required["APP_SECRET_KEY"]
    if secret.lower() in _PLACEHOLDER_SECRETS or secret.lower().startswith(("replace-", "your-")) or len(secret) < 32:
        errors.append("APP_SECRET_KEY must be a generated value with at least 32 characters")

    payment_provider = required["PAYMENT_PROVIDER"].lower()
    if payment_provider not in PAYMENT_PROVIDERS:
        errors.append("PAYMENT_PROVIDER must be mock, toss, or lemon-squeezy")

    try:
        mock_enabled = _bool(values, "MOCK_PAYMENTS_ENABLED")
    except ConfigError as exc:
        errors.append(str(exc))
        mock_enabled = False
    try:
        paid_infrastructure = _bool(values, "PAID_INFRASTRUCTURE")
    except ConfigError as exc:
        errors.append(str(exc))
        paid_infrastructure = True
    if paid_infrastructure:
        errors.append("PAID_INFRASTRUCTURE must be false")
    if payment_provider == "mock" and not mock_enabled:
        errors.append("MOCK_PAYMENTS_ENABLED must be true when PAYMENT_PROVIDER=mock")
    if payment_provider in LIVE_PAYMENT_PROVIDERS and mock_enabled:
        errors.append("MOCK_PAYMENTS_ENABLED must be false when a live provider is selected")
    if app_env == "production" and payment_provider == "mock":
        errors.append("production requires one live payment provider")
    configured_live = [
        name
        for name, keys in {
            "toss": ("TOSS_SECRET_KEY", "TOSS_WEBHOOK_SECRET"),
            "lemon-squeezy": ("LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_WEBHOOK_SECRET"),
        }.items()
        if any(values.get(key, "").strip() for key in keys)
    ]
    if len(configured_live) > 1:
        errors.append("only one live payment provider may be configured per environment")
    if payment_provider == "mock" and configured_live:
        errors.append("live payment credentials cannot be configured when mock is selected")
    if payment_provider in LIVE_PAYMENT_PROVIDERS and configured_live and configured_live != [payment_provider]:
        errors.append("selected payment provider does not match configured live credentials")
    if payment_provider in LIVE_PAYMENT_PROVIDERS:
        required_keys = {
            "toss": ("TOSS_SECRET_KEY",),
            "lemon-squeezy": ("LEMONSQUEEZY_API_KEY",),
        }[payment_provider]
        for key in required_keys:
            if not values.get(key, "").strip():
                errors.append(f"missing required payment provider setting: {key}")

    try:
        payment_sandbox = _bool(
            {"PAYMENT_SANDBOX": values.get("PAYMENT_SANDBOX", "false" if app_env == "production" else "true")},
            "PAYMENT_SANDBOX",
        )
    except ConfigError as exc:
        errors.append(str(exc))
        payment_sandbox = app_env != "production"
    if app_env != "production" and payment_provider in LIVE_PAYMENT_PROVIDERS and not payment_sandbox:
        errors.append("non-production live payment providers require PAYMENT_SANDBOX=true")
    if app_env == "production" and payment_provider in LIVE_PAYMENT_PROVIDERS and payment_sandbox:
        errors.append("production payment providers require PAYMENT_SANDBOX=false")

    auth_provider = values.get("AUTH_PROVIDER", "local-mock").strip().lower()
    if auth_provider not in AUTH_PROVIDERS:
        errors.append("AUTH_PROVIDER must be local-mock or google")
    google_configured = False
    if auth_provider == "google":
        google_keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
        for key in google_keys:
            if not values.get(key, "").strip():
                errors.append(f"missing required Google setting: {key}")
        redirect = values.get("GOOGLE_REDIRECT_URI", "").strip()
        parsed_redirect = urlparse(redirect)
        if redirect and (parsed_redirect.scheme not in {"http", "https"} or not parsed_redirect.netloc):
            errors.append("GOOGLE_REDIRECT_URI must be an absolute http(s) URL")
        google_configured = all(values.get(key, "").strip() for key in google_keys)
    elif app_env == "production" and auth_provider == "local-mock":
        errors.append("production requires AUTH_PROVIDER=google")

    agent_provider = values.get("AGENT_PROVIDER", "local").strip().lower()
    if agent_provider not in AGENT_PROVIDERS:
        errors.append("AGENT_PROVIDER must be local, openai, anthropic, or gemini")
    agent_model = values.get("AGENT_MODEL", "local-echo" if agent_provider == "local" else "").strip()
    if not agent_model:
        errors.append("AGENT_MODEL is required for a non-local Agent provider")
    agent_key = values.get("AGENT_API_KEY", "").strip()
    if agent_provider != "local" and not agent_key:
        errors.append("AGENT_API_KEY is required for a non-local Agent provider")
    agent_base_url = values.get("AGENT_BASE_URL", "").strip() or None
    if agent_base_url:
        parsed_agent_url = urlparse(agent_base_url)
        if parsed_agent_url.scheme not in {"http", "https"} or not parsed_agent_url.netloc:
            errors.append("AGENT_BASE_URL must be an absolute http(s) URL")

    _reject_paid_or_unsafe(values, errors)

    try:
        worker_enabled = _bool(values, "AWS_WORKER_ENABLED")
    except ConfigError as exc:
        errors.append(str(exc))
        worker_enabled = False

    if selected == "free-portfolio":
        if worker_enabled:
            errors.append("free-portfolio must set AWS_WORKER_ENABLED=false")
        if values.get("WORKFLOW_PROVIDER", "").strip() != "local":
            errors.append("free-portfolio requires WORKFLOW_PROVIDER=local")
        if any(
            values.get(key, "").strip()
            for key in (
                "AWS_REGION",
                "AWS_CLUSTER_ARN",
                "AWS_TASK_DEFINITION",
                "AWS_SUBNET_ID",
                "AWS_SECURITY_GROUP_ID",
                "AWS_AUTH_MODE",
                "AWS_WORKER_CAPACITY",
                "AWS_WORKER_ARCH",
                "AWS_WORKER_VCPU",
                "AWS_WORKER_MEMORY_MB",
                "AWS_PUBLIC_SUBNET",
                "AWS_INBOUND_RULES",
            )
        ):
            errors.append("free-portfolio cannot configure AWS worker identifiers")
    elif selected == "aws-worker":
        if not worker_enabled:
            errors.append("aws-worker requires AWS_WORKER_ENABLED=true")
        required_worker = {
            "AWS_REGION": "",
            "AWS_CLUSTER_ARN": "",
            "AWS_TASK_DEFINITION": "",
            "AWS_SUBNET_ID": "",
            "AWS_SECURITY_GROUP_ID": "",
            "AWS_AUTH_MODE": "task-role",
            "AWS_WORKER_CAPACITY": "fargate-spot",
            "AWS_WORKER_ARCH": "arm64",
            "AWS_WORKER_VCPU": "0.25",
            "AWS_WORKER_MEMORY_MB": "512",
            "AWS_PUBLIC_SUBNET": "true",
            "AWS_INBOUND_RULES": "none",
        }
        for key, expected in required_worker.items():
            actual = values.get(key, "").strip()
            if not actual:
                errors.append(f"missing required aws-worker setting: {key}")
            elif expected and actual.lower() != expected.lower():
                errors.append(f"{key} must be {expected}")
        if values.get("WORKFLOW_PROVIDER", "").strip() not in {"local", "inngest"}:
            errors.append("aws-worker requires WORKFLOW_PROVIDER=local or inngest")

    if errors:
        raise ConfigError("configuration rejected:\n- " + "\n- ".join(sorted(set(errors))))

    quota_defaults = (10, 100) if selected == "free-portfolio" else (50, 500)
    quota_max_runs = _bounded_int(values, "RUN_QUOTA_MAX_RUNS", quota_defaults[0], errors, maximum=1_000_000)
    quota_max_units = _bounded_int(values, "RUN_QUOTA_MAX_UNITS", quota_defaults[1], errors, maximum=10_000_000)
    quota_period_seconds = _bounded_int(values, "RUN_QUOTA_PERIOD_SECONDS", 86400, errors, maximum=31_536_000)
    try:
        otel_enabled = _bool({"OTEL_ENABLED": values.get("OTEL_ENABLED", "false")}, "OTEL_ENABLED")
    except ConfigError as exc:
        errors.append(str(exc))
        otel_enabled = False
    otel_sample_rate = _bounded_float(values, "OTEL_SAMPLE_RATE", 0.1, errors)
    otel_exporter = values.get("OTEL_EXPORTER", "memory").strip().lower()
    if otel_exporter not in {"memory", "none", "otlp"}:
        errors.append("OTEL_EXPORTER must be memory, none, or otlp")
    agent_max_output_tokens = _bounded_int(
        values, "AGENT_MAX_OUTPUT_TOKENS", 512, errors, maximum=4096
    )
    agent_timeout_seconds = _bounded_int(
        values, "AGENT_TIMEOUT_SECONDS", 30, errors, maximum=120
    )

    if errors:
        raise ConfigError("configuration rejected:\n- " + "\n- ".join(sorted(set(errors))))

    # Do not return APP_SECRET_KEY or any future secret-bearing value as a
    # first-class field.  The server only needs the validated non-secret view.
    safe_values = {
        key: value
        for key, value in values.items()
        if key not in {
            "APP_SECRET_KEY",
            "DATABASE_URL",
            "GOOGLE_CLIENT_SECRET",
            "TOSS_SECRET_KEY",
            "TOSS_WEBHOOK_SECRET",
            "LEMONSQUEEZY_API_KEY",
            "LEMONSQUEEZY_WEBHOOK_SECRET",
            "AGENT_API_KEY",
        }
    }
    return FoundationConfig(
        app_env=app_env,
        app_base_url=required["APP_BASE_URL"],
        database_url=required["DATABASE_URL"],
        contract_version=required["CONTRACT_VERSION"],
        deployment_profile=selected,
        payment_provider=payment_provider,
        mock_payments_enabled=mock_enabled,
        payment_sandbox=payment_sandbox,
        auth_provider=auth_provider,
        google_configured=google_configured,
        agent_provider=agent_provider,
        agent_model=agent_model,
        agent_max_output_tokens=agent_max_output_tokens,
        agent_timeout_seconds=agent_timeout_seconds,
        agent_base_url=agent_base_url,
        workflow_provider=required["WORKFLOW_PROVIDER"],
        aws_worker_enabled=worker_enabled,
        quota_max_runs=quota_max_runs,
        quota_max_units=quota_max_units,
        quota_period_seconds=quota_period_seconds,
        otel_enabled=otel_enabled,
        otel_sample_rate=otel_sample_rate,
        values=safe_values,
    )


def merged_environment(env_file: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file:
        values.update(load_env_file(env_file))
    # Explicit process values win over templates, which lets a user inject a
    # generated local secret without writing it into the repository.
    values.update({key: value for key, value in os.environ.items() if key.isupper()})
    return values


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate a foundation environment profile")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    try:
        config = validate_profile(merged_environment(args.env_file), args.profile)
    except ConfigError as exc:
        print(str(exc))
        return 2
    print(
        "configuration ok: "
        f"profile={config.deployment_profile} "
        f"contract={config.contract_version} "
        f"worker={'enabled' if config.aws_worker_enabled else 'disabled'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
