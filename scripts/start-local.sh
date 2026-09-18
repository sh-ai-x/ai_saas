#!/usr/bin/env sh
set -eu

env_file=${1:-config/profiles/free-portfolio.example.env}
profile=${DEPLOYMENT_PROFILE:-free-portfolio}
exec python3 -m foundation.server --env-file "$env_file" --profile "$profile" --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"

