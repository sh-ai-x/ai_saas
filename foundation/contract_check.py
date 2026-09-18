"""Deterministic checks for the foundation's versioned contract set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from .config import ConfigError, validate_profile

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_ROOT = ROOT / "packages" / "contracts"


class ContractCheckError(AssertionError):
    pass


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_against_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type and not _type_matches(value, expected_type):
        raise ContractCheckError(f"{path}: expected {expected_type}")
    if "const" in schema and value != schema["const"]:
        raise ContractCheckError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractCheckError(f"{path}: value is outside enum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ContractCheckError(f"{path}: string is too short")
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ContractCheckError(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ContractCheckError(f"{path}: unknown properties {unknown}")
        for key, child_schema in properties.items():
            if key in value:
                validate_against_schema(value[key], child_schema, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_against_schema(item, schema["items"], f"{path}[{index}]")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractCheckError(f"cannot read JSON contract {path}: {exc}") from exc


def check_contracts() -> list[str]:
    if not CONTRACT_ROOT.is_dir():
        raise ContractCheckError("packages/contracts is missing")
    manifest = _read_json(CONTRACT_ROOT / "manifest.json")
    if manifest.get("contract_version") != "v1":
        raise ContractCheckError("contract manifest must declare v1")

    expected_families = {"rest", "sse", "events", "providers"}
    actual_families = {path.relative_to(CONTRACT_ROOT).parts[0] for path in CONTRACT_ROOT.glob("*/v1/*.json")}
    if actual_families != expected_families:
        raise ContractCheckError(
            f"contract families must be exactly {sorted(expected_families)}, got {sorted(actual_families)}"
        )

    schema_count = 0
    for path in sorted(CONTRACT_ROOT.glob("*/v1/*.json")):
        schema = _read_json(path)
        if schema.get("version") != "v1":
            raise ContractCheckError(f"{path}: missing version=v1")
        if not str(schema.get("$id", "")).endswith(f"/{path.stem}.json"):
            raise ContractCheckError(f"{path}: $id must identify the versioned file")
        example = schema.get("x-example")
        if example is None:
            raise ContractCheckError(f"{path}: every contract must include x-example")
        validate_against_schema(example, schema)
        schema_count += 1

    provider_manifest = _read_json(CONTRACT_ROOT / "providers" / "v1" / "capabilities.json")
    provider_ids = {entry["id"] for entry in provider_manifest["x-example"]["providers"]}
    if provider_ids != {"mock", "toss", "lemon-squeezy"}:
        raise ContractCheckError("provider registry must include mock, toss, lemon-squeezy")
    if "provider_sdk" in json.dumps(manifest).lower():
        raise ContractCheckError("domain contract manifest must not depend on provider SDKs")
    return [f"validated {schema_count} versioned JSON contracts", "validated provider registry"]


def check_profiles() -> list[str]:
    common = {
        "APP_ENV": "local",
        "APP_BASE_URL": "http://localhost:8080",
        "DATABASE_URL": "postgresql://foundation@localhost:5432/foundation",
        "APP_SECRET_KEY": "x" * 64,
        "CONTRACT_VERSION": "v1",
        "PAYMENT_PROVIDER": "mock",
        "MOCK_PAYMENTS_ENABLED": "true",
        "PAID_INFRASTRUCTURE": "false",
        "WORKFLOW_PROVIDER": "local",
    }
    free = {**common, "DEPLOYMENT_PROFILE": "free-portfolio", "AWS_WORKER_ENABLED": "false"}
    validate_profile(free, "free-portfolio")
    aws = {
        **common,
        "DEPLOYMENT_PROFILE": "aws-worker",
        "AWS_WORKER_ENABLED": "true",
        "AWS_REGION": "us-east-1",
        "AWS_CLUSTER_ARN": "arn:aws:ecs:local:000000000000:cluster/foundation",
        "AWS_TASK_DEFINITION": "foundation-worker:1",
        "AWS_SUBNET_ID": "subnet-local",
        "AWS_SECURITY_GROUP_ID": "sg-local",
        "AWS_AUTH_MODE": "task-role",
        "AWS_WORKER_CAPACITY": "fargate-spot",
        "AWS_WORKER_ARCH": "arm64",
        "AWS_WORKER_VCPU": "0.25",
        "AWS_WORKER_MEMORY_MB": "512",
        "AWS_PUBLIC_SUBNET": "true",
        "AWS_INBOUND_RULES": "none",
    }
    validate_profile(aws, "aws-worker")

    for name, invalid in (
        ("missing secret", {key: value for key, value in free.items() if key != "APP_SECRET_KEY"}),
        ("free with ALB", {**free, "ALB_ARN": "arn:aws:elasticloadbalancing:paid"}),
        ("aws missing region", {key: value for key, value in aws.items() if key != "AWS_REGION"}),
        ("aws with NAT", {**aws, "NAT_GATEWAY_ID": "nat-paid"}),
    ):
        try:
            validate_profile(invalid, invalid.get("DEPLOYMENT_PROFILE"))
        except ConfigError:
            continue
        raise ContractCheckError(f"profile negative check did not fail closed: {name}")
    return ["validated free-portfolio profile and fail-closed negatives", "validated aws-worker profile and fail-closed negatives"]


def check_worker_deployment_contract() -> list[str]:
    contract = _read_json(ROOT / "infra" / "aws" / "fargate-spot-runtask.json")
    constraints = contract.get("task_definition_constraints", {})
    cost = contract.get("cost_boundary", {})
    request = contract.get("run_task_request", {})
    network = request.get("networkConfiguration", {})
    awsvpc = network.get("awsvpcConfiguration", {})
    security = contract.get("security_boundary", {})
    if contract.get("operation") != "ecs:RunTask":
        raise ContractCheckError("worker deployment contract must describe ECS RunTask")
    if (
        constraints.get("cpu") != "256"
        or constraints.get("vcpu") != "0.25"
        or constraints.get("memory") != "512"
        or constraints.get("memory_mb") != 512
    ):
        raise ContractCheckError("worker task must stay at 0.25 vCPU and 512 MiB")
    if constraints.get("runtime_platform", {}).get("cpu_architecture") != "ARM64":
        raise ContractCheckError("worker task must be ARM64")
    if cost.get("capacity_provider") != "FARGATE_SPOT" or not cost.get("interruptible"):
        raise ContractCheckError("worker task must be interruptible Fargate Spot")
    if cost.get("alb_required") or cost.get("nat_gateway_required") or cost.get("always_on_service"):
        raise ContractCheckError("low-cost worker contract enables a forbidden always-on resource")
    if security.get("inbound_worker_rules") != "none" or security.get("worker_http_listener"):
        raise ContractCheckError("worker deployment contract must have no inbound route")
    if awsvpc.get("assignPublicIp") != "ENABLED":
        raise ContractCheckError("worker contract must provide public-subnet outbound access")
    return ["validated interruptible ARM64 Fargate Spot RunTask contract"]


def run_checks() -> list[str]:
    from services.admin_operations.contract_check import run_contract_checks as run_admin_checks
    from services.billing.contract_check import run_contract_checks as run_billing_checks
    from services.identity_tenant.contract_check import run_contract_checks as run_identity_checks
    from services.run_service.contract_check import run_contract_checks as run_run_checks

    return (
        check_contracts()
        + check_profiles()
        + check_worker_deployment_contract()
        + run_identity_checks()
        + run_admin_checks()
        + run_billing_checks()
        + run_run_checks()
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic foundation contract checks")
    parser.parse_args()
    try:
        for line in run_checks():
            print(f"PASS {line}")
    except (ContractCheckError, OSError, ValueError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
