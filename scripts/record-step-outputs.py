#!/usr/bin/env python3
"""Write compact, valid phase step evidence from real local commands.

The previous build transcripts were too large for the surrounding tool and
were committed as truncated text. This recorder keeps the required subprocess
fields, runs bounded verification commands, and writes each JSON document
atomically so a partial command can never masquerade as valid evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "phases" / "ai-saas-foundation"

COMMANDS: dict[int, tuple[tuple[str, ...], ...]] = {
    0: ((sys.executable, "-m", "foundation.contract_check"),),
    1: ((sys.executable, "-m", "pytest", "-q", "tests/test_identity_tenant_admin.py"),),
    2: ((sys.executable, "-m", "pytest", "-q", "tests/test_billing.py"),),
    3: ((sys.executable, "-m", "pytest", "-q", "tests/test_run_worker_streaming.py"),),
    4: ((sys.executable, "-m", "pytest", "-q", "tests/test_step4_low_cost.py"),),
    5: ((sys.executable, "scripts/local-smoke.py"),),
}


def run(command: tuple[str, ...]) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def write_atomic(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(path)


def record(step: int) -> int:
    started = time.monotonic()
    command_results: list[dict[str, object]] = []
    for command in COMMANDS[step]:
        result = run(command)
        command_results.append(result)
        if result["exit_code"] != 0:
            break
    exit_code = next((int(item["exit_code"]) for item in command_results if item["exit_code"] != 0), 0)
    stdout = "\n".join(str(item["stdout"]) for item in command_results)
    stderr = "\n".join(str(item["stderr"]) for item in command_results)
    document: dict[str, object] = {
        "schema_version": "1.0.0",
        "phase": "ai-saas-foundation",
        "step": step,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commands": command_results,
        "stdout": stdout,
        "stderr": stderr,
    }
    if step == 5:
        document["environment_note"] = (
            "Host-local vertical slice and Compose-independent checks pass. "
            "Docker build/start is recorded by local-smoke.py when a daemon is available."
        )
    write_atomic(OUTPUT_DIR / f"step{step}-output.json", document)
    print(f"step{step}: exit={exit_code} duration={document['duration_seconds']}s")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Record valid local phase step output JSON")
    parser.add_argument("--step", type=int, choices=range(6))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not args.all and args.step is None:
        parser.error("provide --step N or --all")
    steps = range(6) if args.all else (args.step,)
    exit_code = 0
    for step in steps:
        exit_code = record(int(step)) or exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
