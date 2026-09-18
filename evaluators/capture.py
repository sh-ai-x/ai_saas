"""Run the foundation evaluator scenarios and write safe evidence JSON."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from foundation.contract_check import check_profiles
from services.billing.contract_check import run_contract_checks as billing_checks
from services.billing.errors import InsufficientCredits
from services.identity_tenant.contract_check import run_contract_checks as identity_checks
from services.run_service.contract_check import run_contract_checks as run_checks
from services.metering_billing.runtime import SQLiteCreditLedger
from services.admin_operations.contract_check import run_contract_checks as admin_checks


def _ledger_concurrency() -> list[str]:
    ledger = SQLiteCreditLedger(":memory:", initial_balances={"account-evidence": 1})

    def reserve(index: int) -> str:
        try:
            ledger.reserve(
                "tenant-evidence",
                "account-evidence",
                f"run-evidence-{index}",
                1,
                idempotency_key=f"evidence-reserve-{index}",
            )
        except InsufficientCredits:
            return "one reservation rejected atomically"
        return "one reservation accepted atomically"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(reserve, (1, 2)))
    ledger.close()
    if results.count("one reservation accepted atomically") != 1:
        raise AssertionError("credit reservation concurrency was not atomic")
    return ["one reservation accepted atomically", "one reservation rejected atomically"]


def _scenario_functions() -> dict[str, Callable[[], list[str]]]:
    return {
        "auth": identity_checks,
        "admin": admin_checks,
        "payment-replay": billing_checks,
        "ledger-concurrency": _ledger_concurrency,
        "run-recovery": run_checks,
        "profile-boundaries": check_profiles,
    }


def capture_evidence(output: str | Path) -> dict[str, object]:
    definitions = json.loads(
        (Path(__file__).with_name("scenarios.json")).read_text(encoding="utf-8")
    )
    results: list[dict[str, object]] = []
    for scenario in definitions["scenarios"]:
        scenario_id = str(scenario["id"])
        try:
            checks = _scenario_functions()[scenario_id]()
        except Exception as exc:
            results.append(
                {
                    "id": scenario_id,
                    "status": "failed",
                    "checks": [],
                    "error_type": type(exc).__name__,
                }
            )
            continue
        results.append(
            {
                "id": scenario_id,
                "status": "passed",
                "checks": list(checks),
                "sensitive_values_recorded": False,
            }
        )
    document: dict[str, object] = {
        "schema_version": "v1",
        "evidence_kind": "foundation-evaluator",
        "redaction_policy": "identifiers and outcomes only; no request content",
        "scenarios": results,
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture foundation evaluator evidence")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    document = capture_evidence(args.output)
    failed = [item for item in document["scenarios"] if item["status"] != "passed"]
    print(f"evaluator scenarios: {len(document['scenarios']) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
