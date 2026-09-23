#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="$repo_root/.env"
compose_file="$repo_root/docker/prod/compose.yaml"
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
  echo "Create it first with: cp .env.docker.example .env" >&2
  exit 1
fi

if [[ ! -f "$compose_file" ]]; then
  echo "Missing Compose file: $compose_file" >&2
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
compose_project="${COMPOSE_PROJECT_NAME:-ai-saas-${worktree_slug}}"

port_from_container() {
  local container="$1"
  local internal_port="$2"
  (docker port "$container" "$internal_port" 2>/dev/null || true) \
    | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' \
    | head -n 1
}

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

port_block_is_free() {
  port_is_free "$1" && port_is_free "$2" && port_is_free "$3"
}

configured_slot="$(env_file_value DOCKER_LOCAL_SLOT)"
requested_slot="${DOCKER_LOCAL_SLOT:-$configured_slot}"
if [[ -z "$requested_slot" ]]; then
  hash_hex="$(printf '%s' "$compose_project" | shasum -a 256 | awk '{print substr($1, 1, 8)}')"
  requested_slot=$((16#$hash_hex % 40))
fi
if ! [[ "$requested_slot" =~ ^[0-9]+$ ]] || (( requested_slot < 0 || requested_slot > 39 )); then
  echo "DOCKER_LOCAL_SLOT must be an integer between 0 and 39." >&2
  exit 1
fi

existing_web_port="$(port_from_container "${compose_project}-web-1" 3000)"
existing_foundation_port="$(port_from_container "${compose_project}-foundation-1" 8080)"
existing_postgres_port="$(port_from_container "${compose_project}-postgres-1" 5432)"
if [[ -n "$existing_web_port" && -n "$existing_foundation_port" && -n "$existing_postgres_port" ]]; then
  selected_web_port="$existing_web_port"
  selected_foundation_port="$existing_foundation_port"
  selected_postgres_port="$existing_postgres_port"
else
  selected_slot="$requested_slot"
  found_slot=false
  for probe in {0..39}; do
    candidate_slot=$(( (requested_slot + probe) % 40 ))
    candidate_web_port=$((3100 + candidate_slot * 10))
    candidate_foundation_port=$((8180 + candidate_slot * 10))
    candidate_postgres_port=$((55433 + candidate_slot * 10))
    if port_block_is_free "$candidate_web_port" "$candidate_foundation_port" "$candidate_postgres_port"; then
      selected_slot="$candidate_slot"
      selected_web_port="$candidate_web_port"
      selected_foundation_port="$candidate_foundation_port"
      selected_postgres_port="$candidate_postgres_port"
      found_slot=true
      break
    fi
  done
  if [[ "$found_slot" != true ]]; then
    echo "No free Docker port block found for $compose_project (searched 40 slots)." >&2
    exit 1
  fi
fi

# Shell assignments are the explicit escape hatch. Otherwise every worktree
# gets a stable, collision-checked host-port block. Internal Compose ports do
# not change because service-to-service URLs use the private network.
export WEB_PORT="${WEB_PORT:-$selected_web_port}"
export FOUNDATION_PORT="${FOUNDATION_PORT:-$selected_foundation_port}"
export POSTGRES_PORT="${POSTGRES_PORT:-$selected_postgres_port}"
export FOUNDATION_PUBLIC_URL="${FOUNDATION_PUBLIC_URL:-http://localhost:${FOUNDATION_PORT}}"
export WEB_PUBLIC_URL="${WEB_PUBLIC_URL:-http://localhost:${WEB_PORT}}"
export BETTER_AUTH_URL="${BETTER_AUTH_URL:-http://localhost:${WEB_PORT}}"

# Keep the current checkout as an optional read-only server-side repository.
# The browser picker independently imports a selected directory into the
# foundation state volume, so arbitrary folder selection does not require a
# host-path environment variable or host write access.
configured_repository_host_root="${LOCAL_REPOSITORY_HOST_ROOT:-$(env_file_value LOCAL_REPOSITORY_HOST_ROOT)}"
export LOCAL_REPOSITORY_HOST_ROOT="${configured_repository_host_root:-$repo_root}"
configured_repository_container_root="${LOCAL_REPOSITORY_CONTAINER_ROOT:-$(env_file_value LOCAL_REPOSITORY_CONTAINER_ROOT)}"
if [[ -z "$configured_repository_container_root" ]]; then
  configured_repository_container_root="/local-repositories/$(basename -- "$LOCAL_REPOSITORY_HOST_ROOT")"
fi
export LOCAL_REPOSITORY_CONTAINER_ROOT="$configured_repository_container_root"
configured_repository_roots="${LOCAL_REPOSITORY_ROOTS:-$(env_file_value LOCAL_REPOSITORY_ROOTS)}"
export LOCAL_REPOSITORY_ROOTS="${configured_repository_roots:-/local-repositories}"
configured_repository_git_common_root="${LOCAL_REPOSITORY_GIT_COMMON_ROOT:-$(env_file_value LOCAL_REPOSITORY_GIT_COMMON_ROOT)}"
if [[ -z "$configured_repository_git_common_root" ]]; then
  git_common_dir="$(git -C "$repo_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  if [[ -n "$git_common_dir" ]]; then
    configured_repository_git_common_root="$(cd -- "$(dirname -- "$git_common_dir")" && pwd)"
  fi
fi
export LOCAL_REPOSITORY_GIT_COMMON_ROOT="${configured_repository_git_common_root:-$repo_root}"

# docker:local is a local profile. Never let a copied Neon URL silently make
# migrations or browser traffic target a cloud database. A remote target is
# possible only with an explicit opt-in for diagnostics.
local_database_url="postgresql://foundation@postgres:5432/foundation"
configured_database_url="${WEB_DATABASE_URL:-$(env_file_value WEB_DATABASE_URL)}"
configured_migration_url="${WEB_DATABASE_URL_UNPOOLED:-$(env_file_value WEB_DATABASE_URL_UNPOOLED)}"
allow_remote_database="${ALLOW_REMOTE_DATABASE:-$(env_file_value ALLOW_REMOTE_DATABASE)}"
if [[ "$allow_remote_database" != "true" ]]; then
  if [[ "$configured_database_url" == *neon.tech* || "$configured_migration_url" == *neon.tech* ]]; then
    echo "A Neon URL was found; forcing the local Compose database for docker:local."
  fi
  export WEB_DATABASE_URL="$local_database_url"
  export WEB_DATABASE_URL_UNPOOLED="$local_database_url"
else
  if [[ -z "$configured_database_url" || -z "$configured_migration_url" ]]; then
    echo "ALLOW_REMOTE_DATABASE=true requires WEB_DATABASE_URL and WEB_DATABASE_URL_UNPOOLED." >&2
    exit 1
  fi
  export WEB_DATABASE_URL="$configured_database_url"
  export WEB_DATABASE_URL_UNPOOLED="$configured_migration_url"
fi

if [[ -z "${APP_SECRET_KEY:-}" && -z "$(env_file_value APP_SECRET_KEY)" ]]; then
  generated_app_secret="$(openssl rand -hex 32)"
  export APP_SECRET_KEY="$generated_app_secret"
  echo "APP_SECRET_KEY was empty; generated an ephemeral value for this run."
fi

local_compose_file="$repo_root/docker/local/compose.yaml"
if [[ ! -f "$local_compose_file" ]]; then
  echo "Missing local Compose override: $local_compose_file" >&2
  exit 1
fi

compose=(docker compose --project-name "$compose_project" --env-file "$env_file" -f "$compose_file" -f "$local_compose_file")
cd "$repo_root"

if [[ "$command_mode" == "down" ]]; then
  down_args=()
  if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
    down_args+=(--volumes)
    shift
  fi
  if (( $# > 0 )); then
    echo "Usage: pnpm docker:local [down [--volumes]]" >&2
    exit 2
  fi
  "${compose[@]}" down "${down_args[@]}"
  exit 0
fi

if ! "${compose[@]}" up -d --build --force-recreate "$@"; then
  echo >&2
  echo "Docker Compose failed. Recent dependency logs:" >&2
  "${compose[@]}" ps >&2 || true
  "${compose[@]}" logs --no-color --tail=120 web-migrate foundation >&2 || true
  exit 1
fi

"${compose[@]}" ps
