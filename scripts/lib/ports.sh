# scripts/lib/ports.sh — single source of truth for every host +
# container port used by docker:local / docker:neon. Source from any
# bash script that needs a port; do not hardcode ports elsewhere.
# Rules encoded: ADR-0002 (docs/adr/0002-worktree-port-and-database-isolation.md).
#   - Container ports stable: web=3000, foundation=8080, postgres=5432.
#   - Host web ports pinned across worktrees: local=3100, stage=3200.
#   - Foundation + postgres host ports keep the slot-allocation block
#     for collision-free concurrent worktrees (web ports do NOT slot).

# shellcheck shell=bash
readonly DOCKER_WEB_CONTAINER_PORT=3000
readonly DOCKER_FOUNDATION_CONTAINER_PORT=8080
readonly DOCKER_POSTGRES_CONTAINER_PORT=5432

readonly DOCKER_LOCAL_WEB_HOST_PORT=3100
readonly DOCKER_STAGE_WEB_HOST_PORT=3200

readonly DOCKER_LOCAL_FOUNDATION_PORT_BASE=8180
readonly DOCKER_LOCAL_POSTGRES_PORT_BASE=55433
readonly DOCKER_STAGE_FOUNDATION_PORT_BASE=8280
readonly DOCKER_SLOT_COUNT=40

# Export so docker compose inherits the values via the shell env.
# Compose files default to the same numbers so a bare `docker compose
# config` still validates without sourcing this lib.
export DOCKER_WEB_CONTAINER_PORT
export DOCKER_FOUNDATION_CONTAINER_PORT
export DOCKER_POSTGRES_CONTAINER_PORT
export DOCKER_LOCAL_WEB_HOST_PORT
export DOCKER_STAGE_WEB_HOST_PORT
export DOCKER_LOCAL_FOUNDATION_PORT_BASE
export DOCKER_LOCAL_POSTGRES_PORT_BASE
export DOCKER_STAGE_FOUNDATION_PORT_BASE
export DOCKER_SLOT_COUNT
