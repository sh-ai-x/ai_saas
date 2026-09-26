#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="${NEON_DOCKER_ENV_FILE:-$repo_root/.env.staging}"
command_mode="up"
if [[ "${1:-}" == "down" ]]; then
  command_mode="down"
  shift
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Start Docker Desktop and try again." >&2
  exit 1
fi
if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file" >&2
  echo "Create it first with: cp .env.staging.example .env.staging" >&2
  exit 1
fi

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
compose_project="${NEON_COMPOSE_PROJECT_NAME:-ai-saas-neon-${worktree_slug}}"

port_from_container() {
  local container="$1"
  local internal_port="$2"
  { docker port "$container" "$internal_port" 2>/dev/null || true; } \
    | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' \
    | head -n 1
}

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

port_block_is_free() {
  port_is_free "$1" && port_is_free "$2"
}

configured_slot="${NEON_DOCKER_SLOT:-}"
if [[ -z "$configured_slot" ]]; then
  hash_hex="$(printf '%s' "$compose_project" | shasum -a 256 | awk '{print substr($1, 1, 8)}')"
  configured_slot=$((16#$hash_hex % 40))
fi
if ! [[ "$configured_slot" =~ ^[0-9]+$ ]] || (( configured_slot < 0 || configured_slot > 39 )); then
  echo "NEON_DOCKER_SLOT must be an integer between 0 and 39." >&2
  exit 1
fi

existing_web_port="$(port_from_container "${compose_project}-web-1" 3000)"
existing_foundation_port="$(port_from_container "${compose_project}-foundation-1" 8080)"
if [[ -n "$existing_web_port" && -n "$existing_foundation_port" ]]; then
  selected_web_port="$existing_web_port"
  selected_foundation_port="$existing_foundation_port"
else
  found_slot=false
  for probe in {0..39}; do
    candidate_slot=$(( (configured_slot + probe) % 40 ))
    candidate_web_port=$((3200 + candidate_slot * 10))
    candidate_foundation_port=$((8280 + candidate_slot * 10))
    if port_block_is_free "$candidate_web_port" "$candidate_foundation_port"; then
      selected_web_port="$candidate_web_port"
      selected_foundation_port="$candidate_foundation_port"
      found_slot=true
      break
    fi
  done
  if [[ "$found_slot" != true ]]; then
    echo "No free Neon Docker port block found for $compose_project (searched 40 slots)." >&2
    exit 1
  fi
fi

export WEB_PORT="${WEB_PORT:-$selected_web_port}"
export FOUNDATION_PORT="${FOUNDATION_PORT:-$selected_foundation_port}"
export FOUNDATION_PUBLIC_URL="${FOUNDATION_PUBLIC_URL:-http://localhost:${FOUNDATION_PORT}}"
export WEB_PUBLIC_URL="${WEB_PUBLIC_URL:-http://localhost:${WEB_PORT}}"
export BETTER_AUTH_URL="${BETTER_AUTH_URL:-http://localhost:${WEB_PORT}}"

compose=(docker compose --project-name "$compose_project" --env-file "$env_file" -f "$repo_root/docker/neon/compose.yaml")
cd "$repo_root"

if [[ "$command_mode" == "down" ]]; then
  if (( $# > 0 )); then
    echo "Usage: pnpm docker:neon [down]" >&2
    exit 2
  fi
  "${compose[@]}" down
  exit 0
fi

"${compose[@]}" up -d --build --force-recreate "$@"
"${compose[@]}" ps
