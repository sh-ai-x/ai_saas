#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null 2>&1 || {
  echo "verify-local.sh: uv is required; install it from https://docs.astral.sh/uv/" >&2
  exit 1
}
uv sync --locked
uv run --locked python -m compileall -q foundation services lib evaluators tests
uv run --locked python -m foundation.contract_check
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m lib.intent_integrity --pre ai-saas-foundation

evidence_path="${TMPDIR:-/tmp}/ai-saas-foundation-evidence.json"
uv run --locked python -m evaluators.capture --output "$evidence_path"
uv run --locked python - "$evidence_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
assert document["schema_version"] == "v1"
assert document["scenarios"]
assert all(item["status"] == "passed" for item in document["scenarios"])
print(f"evidence: {len(document['scenarios'])} scenarios passed")
PY

if command -v docker >/dev/null 2>&1; then
  APP_SECRET_KEY="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    docker compose -f docker/dev/compose.yaml config >/dev/null
  echo "docker compose config: PASS"
else
  echo "docker compose config: SKIP (docker is not installed)"
fi
