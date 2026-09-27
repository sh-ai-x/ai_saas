#!/usr/bin/env bash
# verify-docker.sh — thin wrapper around verify-docker-env.sh that
# derives the compose project + env file from the profile + current
# branch. Lets `pnpm docker:verify` run as a standalone command
# without going through `docker:local` / `docker:neon` first.
#
# Usage:
#   verify-docker.sh [local|neon]
#
# Exit codes match verify-docker-env.sh (0 = pass, 1 = missing/empty vars).

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
# shellcheck source=lib/ports.sh
source "$repo_root/scripts/lib/ports.sh"
verify_script="$repo_root/scripts/verify-docker-env.sh"

profile="${1:-}"
case "$profile" in
  local)
    env_file="$repo_root/.env.local"
    ;;
  neon|stage|staging)
    env_file="${NEON_DOCKER_ENV_FILE:-$repo_root/.env.staging}"
    profile="neon"
    ;;
  "")
    echo "Usage: $0 [local|neon]" >&2
    echo "  local: verify the docker:local compose project (default port 3100)" >&2
    echo "  neon:  verify the docker:neon compose project  (default port 3200)" >&2
    exit 2
    ;;
  *)
    echo "Unknown profile: $profile (expected local or neon)" >&2
    exit 2
    ;;
esac

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file" >&2
  echo "Run \`pnpm docker:${profile}\` once first, or copy the matching .example file." >&2
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

if [[ "$profile" == "neon" ]]; then
  compose_project="${NEON_COMPOSE_PROJECT_NAME:-ai-saas-neon-${worktree_slug}}"
else
  compose_project="${COMPOSE_PROJECT_NAME:-ai-saas-${worktree_slug}}"
fi

exec "$verify_script" "$compose_project" "$env_file"
