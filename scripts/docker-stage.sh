#!/usr/bin/env bash

# Stage orchestrator.
#
# - Composes the production-shape images against a Neon cloud DB.
# - Allocates a stable host-port block (3200/8280/56433 + slot*10) so stage
#   never collides with `docker:local` (3100/8180/55433 range).
# - Refuses to run without DATABASE_URL / DATABASE_URL_UNPOOLED /
#   BETTER_AUTH_SECRET / APP_SECRET_KEY. Stage never falls back to the
#   local container DB the way docker:local does.

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="$repo_root/.env"
compose_file="$repo_root/docker/prod/compose.yaml"
override_file="$repo_root/docker/stage/compose.yaml"
command_mode="up"

if [[ "${1:-}" == "down" ]]; then
  command_mode="down"
  shift
fi

for required in docker; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "$required is required." >&2
    exit 1
  fi
done

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file" >&2
  echo "Create it first with: cp .env.docker.example .env" >&2
  exit 1
fi

if [[ ! -f "$compose_file" ]]; then
  echo "Missing Compose file: $compose_file" >&2
  exit 1
fi

if [[ ! -f "$override_file" ]]; then
  echo "Missing stage override: $override_file" >&2
  exit 1
fi

env_file_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^\"|\"$/, "", value)
      print value
      exit
    }
  ' "$env_file"
}

sanitize_slug() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9_-]+/-/g; s/^-+//; s/-+$//' \
    | cut -c1-48
}

branch_name="$(git -C "$repo_root" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ -z "$branch_name" ]]; then
  branch_name="detached-$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || printf 'worktree')"
fi
worktree_slug="$(sanitize_slug "$branch_name")"
compose_project="${COMPOSE_PROJECT_NAME:-ai-saas-stage-${worktree_slug}}"

# Stage refuses to run without a Neon DB. A missing pooled URL is a fatal
# config error, not a warning.
for _key in DATABASE_URL DATABASE_URL_UNPOOLED BETTER_AUTH_SECRET APP_SECRET_KEY; do
  _val="${!_key:-$(env_file_value "$_key")}"
  if [[ -z "$_val" ]]; then
    echo "Stage requires $_key in the environment or $env_file." >&2
    exit 1
  fi
  export "$_key"="$_val"
done

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

port_block_is_free() {
  port_is_free "$1" && port_is_free "$2"
}

configured_slot="$(env_file_value DOCKER_STAGE_SLOT)"
requested_slot="${DOCKER_STAGE_SLOT:-$configured_slot}"
if [[ -z "$requested_slot" ]]; then
  hash_hex="$(printf '%s' "$compose_project" | shasum -a 256 | awk '{print substr($1, 1, 8)}')"
  requested_slot=$((16#$hash_hex % 40))
fi
if ! [[ "$requested_slot" =~ ^[0-9]+$ ]] || (( requested_slot < 0 || requested_slot > 39 )); then
  echo "DOCKER_STAGE_SLOT must be an integer between 0 and 39." >&2
  exit 1
fi

existing_web_port="$(docker port "${compose_project}-web-1" 3000 2>/dev/null | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | head -n 1)"
existing_foundation_port="$(docker port "${compose_project}-foundation-1" 8080 2>/dev/null | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | head -n 1)"
if [[ -n "$existing_web_port" && -n "$existing_foundation_port" ]]; then
  selected_web_port="$existing_web_port"
  selected_foundation_port="$existing_foundation_port"
else
  found_slot=false
  for probe in {0..39}; do
    candidate_slot=$(( (requested_slot + probe) % 40 ))
    candidate_web_port=$((3200 + candidate_slot * 10))
    candidate_foundation_port=$((8280 + candidate_slot * 10))
    if port_block_is_free "$candidate_web_port" "$candidate_foundation_port"; then
      selected_slot="$candidate_slot"
      selected_web_port="$candidate_web_port"
      selected_foundation_port="$candidate_foundation_port"
      found_slot=true
      break
    fi
  done
  if [[ "$found_slot" != true ]]; then
    echo "No free stage port block found for $compose_project (searched 40 slots)." >&2
    exit 1
  fi
fi

export WEB_PORT="${WEB_PORT:-$selected_web_port}"
export FOUNDATION_PORT="${FOUNDATION_PORT:-$selected_foundation_port}"
export FOUNDATION_PUBLIC_URL="${FOUNDATION_PUBLIC_URL:-http://localhost:${FOUNDATION_PORT}}"
export WEB_PUBLIC_URL="${WEB_PUBLIC_URL:-http://localhost:${WEB_PORT}}"
export BETTER_AUTH_URL="${BETTER_AUTH_URL:-http://localhost:${WEB_PORT}}"

# Optional local Postgres (rare — stage prefers Neon).
if [[ "${LOCAL_POSTGRES:-false}" == "true" ]]; then
  export POSTGRES_PORT="${POSTGRES_PORT:-$((56433 + selected_slot * 10))}"
  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-local-postgres}"
fi

compose=(docker compose --project-name "$compose_project" --env-file "$env_file" -f "$compose_file" -f "$override_file")
cd "$repo_root"

if [[ "$command_mode" == "down" ]]; then
  down_args=()
  if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
    down_args+=(--volumes)
    shift
  fi
  if (( $# > 0 )); then
    echo "Usage: pnpm docker:stage [down [--volumes]]" >&2
    exit 2
  fi
  "${compose[@]}" down "${down_args[@]}"
  exit 0
fi

echo "Stage stack:"
echo "  project:     $compose_project"
echo "  web:         http://localhost:${WEB_PORT}"
echo "  foundation:  http://localhost:${FOUNDATION_PORT}"
echo "  slot:        ${selected_slot:-reused}"

if ! "${compose[@]}" up -d --build --force-recreate "$@"; then
  echo >&2
  echo "Docker Compose failed. Recent dependency logs:" >&2
  "${compose[@]}" ps >&2 || true
  "${compose[@]}" logs --no-color --tail=120 web-migrate foundation >&2 || true
  exit 1
fi

"${compose[@]}" ps