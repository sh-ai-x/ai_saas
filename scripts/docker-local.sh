#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
env_file="$repo_root/.env"
compose_file="$repo_root/docker/prod/compose.yaml"

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

if [[ -z "${APP_SECRET_KEY:-}" && -z "$(env_file_value APP_SECRET_KEY)" ]]; then
  generated_app_secret="$(openssl rand -hex 32)"
  export APP_SECRET_KEY="$generated_app_secret"
  echo "APP_SECRET_KEY was empty; generated an ephemeral value for this run."
fi

compose=(docker compose --env-file "$env_file" -f "$compose_file")
cd "$repo_root"

if ! "${compose[@]}" up -d --build --force-recreate "$@"; then
  echo >&2
  echo "Docker Compose failed. Recent dependency logs:" >&2
  "${compose[@]}" ps >&2 || true
  "${compose[@]}" logs --no-color --tail=120 web-migrate foundation >&2 || true
  exit 1
fi

"${compose[@]}" ps
