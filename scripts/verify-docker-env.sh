#!/usr/bin/env bash
# verify-docker-env.sh — confirm env vars reach the running docker containers.
#
# Self-contained: pure bash + awk + grep. No python, no jq required.
# Called from scripts/docker-local.sh and scripts/docker-neon.sh after
# `docker compose … up -d` succeeds. Exits 0 if all required-vars are
# present (warnings allowed), 1 if any required-var is missing.
#
# Usage: verify-docker-env.sh <compose-project> <env-file>
#
# Categories (per docker/prod/compose.yaml, docker/local/compose.yaml,
# docker/neon/compose.yaml):
#   DB          — DATABASE_URL on foundation, web-migrate, web
#                 POSTGRES_* on postgres (when present)
#   TOSS        — TOSS_CLIENT_KEY / TOSS_SECRET_KEY / TOSS_WEBHOOK_SECRET
#                 on foundation + web. Empty values downgrade to WARN
#                 when PAYMENT_PROVIDER=mock (docker:local override).
#   JEV         — JEV_API_KEY on web
#   OPENAI      — OPENAI_API_KEY on foundation + web
#   GOOGLE_OAUTH — GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / BETTER_AUTH_SECRET
#                  NEXT_PUBLIC_GOOGLE_AUTH_ENABLED on web (must be true)

set -uo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: verify-docker-env.sh <compose-project> <env-file>" >&2
  exit 2
fi

COMPOSE_PROJECT="$1"
ENV_FILE="$2"

if ! command -v docker >/dev/null 2>&1; then
  echo "verify-docker-env: docker is not installed; skipping." >&2
  exit 0
fi

# Discover running services. `docker compose ps --services` works against
# the live project. We fall back to a hardcoded list of expected services
# when the compose project is unavailable (e.g. containers crashed).
# `mapfile` requires bash 4+, so use a while-read loop for bash 3.2 (macOS).
SERVICES=()
while IFS= read -r svc; do
  SERVICES+=("$svc")
done < <(docker compose --project-name "$COMPOSE_PROJECT" ps --services 2>/dev/null) || true
if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=(foundation web web-migrate postgres)
fi

# Dump env for one service (one KEY=VALUE per line).
service_env() {
  local service="$1"
  local container="${COMPOSE_PROJECT}-${service}-1"
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" 2>/dev/null
}

# Read a value from a KEY=VALUE stream; empty string when absent.
read_kv() {
  local key="$1"
  local stream="$2"
  printf '%s\n' "$stream" | awk -F= -v k="$key" '$1 == k { sub(/^[^=]*=/, ""); print; exit }'
}

# Read a value from the env-file (used to short-circuit checks for vars the
# compose layer injects from the shell, not the env-file).
envfile_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  awk -F= -v k="$key" '
    $1 == k {
      v = substr($0, index($0, "=") + 1)
      gsub(/^\"|\"$/, "", v)
      print v
      exit
    }
  ' "$ENV_FILE"
}

# Pretty status
PASS=0; WARN=0; FAIL=0
declare -a ROWS

# classify <category> <service> <key> <value> [<tolerated_empty=0|1>]
classify() {
  local category="$1" service="$2" key="$3" value="$4" tolerate_empty="${5:-0}"
  local status="PASS" detail="set"
  if [[ -z "$value" ]]; then
    if [[ "$tolerate_empty" == "1" ]]; then
      status="WARN"; detail="empty (mock-mode tolerated)"
      WARN=$((WARN + 1))
    else
      status="FAIL"; detail="missing or empty"
      FAIL=$((FAIL + 1))
    fi
  else
    PASS=$((PASS + 1))
  fi
  ROWS+=("$category|$service|$key|$status|$detail")
}

for service in "${SERVICES[@]}"; do
  container="${COMPOSE_PROJECT}-${service}-1"
  if ! docker inspect "$container" >/dev/null 2>&1; then
    ROWS+=("BOOT|$service|container|FAIL|not running")
    FAIL=$((FAIL + 1))
    continue
  fi
  env="$(service_env "$service")"
  payment_provider="$(read_kv PAYMENT_PROVIDER "$env")"
  [[ -z "$payment_provider" ]] && payment_provider="$(envfile_value PAYMENT_PROVIDER)"
  toss_tolerate=0
  if [[ "$payment_provider" == "mock" ]]; then
    toss_tolerate=1
  fi

  # DB
  if [[ "$service" == "foundation" ]]; then
    classify DB "$service" DATABASE_URL "$(read_kv DATABASE_URL "$env")"
  fi
  if [[ "$service" == "web-migrate" ]]; then
    classify DB "$service" WEB_DATABASE_URL_UNPOOLED "$(read_kv DATABASE_URL "$env")"
  fi
  if [[ "$service" == "web" ]]; then
    classify DB "$service" DATABASE_URL "$(read_kv DATABASE_URL "$env")"
  fi
  if [[ "$service" == "postgres" ]]; then
    classify DB "$service" POSTGRES_USER "$(read_kv POSTGRES_USER "$env")"
    classify DB "$service" POSTGRES_DB "$(read_kv POSTGRES_DB "$env")"
  fi

  # Toss
  if [[ "$service" == "foundation" || "$service" == "web" ]]; then
    classify TOSS "$service" TOSS_CLIENT_KEY "$(read_kv TOSS_CLIENT_KEY "$env")" "$toss_tolerate"
    classify TOSS "$service" TOSS_SECRET_KEY "$(read_kv TOSS_SECRET_KEY "$env")" "$toss_tolerate"
    classify TOSS "$service" TOSS_WEBHOOK_SECRET "$(read_kv TOSS_WEBHOOK_SECRET "$env")" "$toss_tolerate"
  fi

  # JEV
  if [[ "$service" == "web" ]]; then
    classify JEV "$service" JEV_API_KEY "$(read_kv JEV_API_KEY "$env")"
  fi

  # OpenAI
  if [[ "$service" == "foundation" || "$service" == "web" ]]; then
    classify OPENAI "$service" OPENAI_API_KEY "$(read_kv OPENAI_API_KEY "$env")"
  fi

  # Google OAuth
  if [[ "$service" == "web" ]]; then
    classify GOOGLE_OAUTH "$service" GOOGLE_CLIENT_ID "$(read_kv GOOGLE_CLIENT_ID "$env")"
    classify GOOGLE_OAUTH "$service" GOOGLE_CLIENT_SECRET "$(read_kv GOOGLE_CLIENT_SECRET "$env")"
    classify GOOGLE_OAUTH "$service" NEXT_PUBLIC_GOOGLE_AUTH_ENABLED "$(read_kv NEXT_PUBLIC_GOOGLE_AUTH_ENABLED "$env")"
    classify GOOGLE_OAUTH "$service" BETTER_AUTH_SECRET "$(read_kv BETTER_AUTH_SECRET "$env")"
  fi
done

# Render table
echo
echo "verify-docker-env: project=${COMPOSE_PROJECT} env_file=${ENV_FILE}"
printf '%-13s %-12s %-32s %-6s %s\n' CATEGORY SERVICE KEY STATUS DETAIL
printf '%-13s %-12s %-32s %-6s %s\n' -------- -------- --- ------ -----
last_cat=""
for row in "${ROWS[@]}"; do
  IFS='|' read -r cat svc key status detail <<<"$row"
  printf '%-13s %-12s %-32s %-6s %s\n' "$cat" "$svc" "$key" "$status" "$detail"
done
echo
echo "summary: pass=${PASS} warn=${WARN} fail=${FAIL}"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
