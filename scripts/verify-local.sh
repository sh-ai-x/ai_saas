#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q foundation services lib evaluators tests
python3 -m foundation.contract_check
python3 -m unittest discover -s tests -v
python3 -m lib.intent_integrity --pre ai-saas-foundation

evidence_path="${TMPDIR:-/tmp}/ai-saas-foundation-evidence.json"
python3 -m evaluators.capture --output "$evidence_path"
python3 - "$evidence_path" <<'PY'
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
  APP_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
    docker compose -f docker/dev/compose.yaml config >/dev/null
  echo "docker compose config: PASS"
else
  echo "docker compose config: SKIP (docker is not installed)"
fi
