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

# ERR trap: tear down the partial stack on compose failure or operator
# interrupt (SIGINT). We only own state we created in this process, so it
# is safe to delete on either signal.
on_err() {
  local rc=$?
  echo "Stage script exited with rc=${rc}; attempting partial-stack cleanup." >&2
  if [[ -n "${compose_cmd:-}" ]]; then
    "${compose_cmd[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "${rc}"
}
trap on_err ERR INT

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

# Load .env into the shell. `set -a; source` lets bash's own parser handle
# quoting, comments, and `export` prefixes — replacing the hand-rolled awk
# parser. .env values are now in the process environment and may shadow
# pre-set env vars; that is intentional for "compose reads from .env".
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

# Stage refuses to run without a Neon DB. A missing pooled URL is a fatal
# config error, not a warning. Values come from .env (sourced above) or the
# pre-existing process environment (whichever is non-empty).
for _key in DATABASE_URL DATABASE_URL_UNPOOLED BETTER_AUTH_SECRET APP_SECRET_KEY; do
  _val="${!_key:-}"
  if [[ -z "$_val" ]]; then
    echo "Stage requires $_key in $env_file or the process environment." >&2
    exit 1
  fi
  export "$_key"="$_val"
done

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

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

port_block_is_free() {
  port_is_free "$1" && port_is_free "$2"
}

# Slot derivation MUST hash the absolute worktree path, NOT the compose
# project name. Two worktrees that share a branch name would otherwise both
# slug to the same compose_project and collide on slot 0.
worktree_root="$(git -C "$repo_root" rev-parse --show-toplevel)"
configured_slot="${DOCKER_STAGE_SLOT:-${DOCKER_STAGE_SLOT_DEFAULT:-}}"
requested_slot="$configured_slot"
if [[ -z "$requested_slot" ]]; then
  hash_hex="$(printf '%s' "$worktree_root" | shasum -a 256 | awk '{print substr($1, 1, 8)}')"
  requested_slot=$((16#$hash_hex % 40))
fi
if ! [[ "$requested_slot" =~ ^[0-9]+$ ]] || (( requested_slot < 0 || requested_slot > 39 )); then
  echo "DOCKER_STAGE_SLOT must be an integer between 0 and 39." >&2
  exit 1
fi

# Probe service existence via probe_container; capture stderr to a log file
# so the operator can see why a port lookup failed (compose v2 changed the
# service-suffix convention once already; if it changes again, we want a
# breadcrumb, not silence).
probe_stderr_log="$(mktemp -t docker-stage-probe.XXXXXX.log)"
probe_container() {
  local svc="$1" internal_port="$2" project="$3"
  local probe_out
  if ! probe_out="$(docker port "${project}-${svc}-1" "$internal_port" 2>"$probe_stderr_log")"; then
    echo "Probe failed for ${project}-${svc}-1:${internal_port}; recent stderr:" >&2
    tail -5 "$probe_stderr_log" >&2 || true
    return 1
  fi
  printf '%s\n' "$probe_out" | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | head -n 1
}
existing_web_port="$(probe_container web 3000 "$compose_project" || true)"
existing_foundation_port="$(probe_container foundation 8080 "$compose_project" || true)"
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

compose_cmd=(docker compose --project-name "$compose_project" --env-file "$env_file" -f "$compose_file" -f "$override_file")
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
  "${compose_cmd[@]}" down "${down_args[@]}"
  exit 0
fi

echo "Stage stack:"
echo "  project:     $compose_project"
echo "  web:         http://localhost:${WEB_PORT}"
echo "  foundation:  http://localhost:${FOUNDATION_PORT}"
echo "  slot:        ${selected_slot:-reused}"

# Validate `$@` passthrough — only allow a known-good flag subset so we
# never accidentally proxy destructive or unknown flags into compose.
allowed_flag() {
  case "$1" in
    --no-cache|-V|--quiet|-q) return 0 ;;
    *) return 1 ;;
  esac
}
up_args=()
for arg in "$@"; do
  if allowed_flag "$arg"; then
    up_args+=("$arg")
  else
    echo "Refusing unknown flag passed to docker:stage: '$arg'" >&2
    echo "Allowed passthrough: --no-cache, -V, --quiet, -q" >&2
    exit 2
  fi
done

if ! "${compose_cmd[@]}" up -d --build --force-recreate "${up_args[@]}"; then
  echo >&2
  echo "Docker Compose failed. Recent dependency logs:" >&2
  "${compose_cmd[@]}" ps >&2 || true
  "${compose_cmd[@]}" logs --no-color --tail=120 web-migrate foundation >&2 || true
  exit 1
fi

"${compose_cmd[@]}" ps