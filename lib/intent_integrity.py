"""Minimal repository-local intent integrity gate for the foundation phase."""

from __future__ import annotations

import argparse
import sys

from foundation.contract_check import run_checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a phase intent integrity pre-check")
    parser.add_argument("--pre", required=True)
    args = parser.parse_args(argv)
    if args.pre != "ai-saas-foundation":
        print(f"unsupported phase: {args.pre}", file=sys.stderr)
        return 2
    try:
        for line in run_checks():
            print(f"PASS {line}")
    except Exception as exc:  # keep the gate's failure output concise and deterministic
        print(f"FAIL intent integrity: {exc}", file=sys.stderr)
        return 1
    print("PASS intent integrity: ai-saas-foundation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

