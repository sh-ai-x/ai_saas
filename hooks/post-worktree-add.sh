#!/usr/bin/env bash
# post-worktree-add.sh — PostToolUse:Bash hook (advisory, never blocks).
#
# Self-contained: does NOT depend on the dev-kit plugin. Wired via
# `.claude/settings.json` so it survives dev-kit upgrades.
#
# When `git worktree add …` succeeds, copy `.env.local` and `.env.staging`
# from the main checkout into the new worktree so a fresh branch is
# immediately runnable for `pnpm docker:local` / `pnpm docker:neon`.
# Both files are gitignored (`.gitignore:10` blanket `.env.*`), so the
# worktree would otherwise be missing them.
#
# Payload shape: Claude Code sends a JSON object on stdin with
# `tool_input.command` (the bash command string), `tool_input.cwd`, and
# `cwd`. We only need command + cwd.

set -uo pipefail

INPUT="$(cat)"

if ! command -v jq >/dev/null 2>&1; then
  printf 'post-worktree-add.sh: jq not installed; skipping env-file copy.\n' >&2
  exit 0
fi

COMMAND="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)"
CWD="$(printf '%s' "$INPUT" | jq -r '.tool_input.cwd // .cwd // ""' 2>/dev/null)"

# Match `git worktree add` (any flags, any path). Allow leading whitespace.
if ! printf '%s' "$COMMAND" | grep -qE '\<git[[:space:]]+worktree[[:space:]]+add\b'; then
  exit 0
fi

# Extract the worktree path. Patterns seen in this repo:
#   git worktree add -b feat/foo .worktrees/foo origin/main
#   git worktree add -b feat/foo /tmp/extra origin/main
# The worktree path is the first non-flag, non-branch, non-base-ref arg.
# Heuristic: take the last token that is a directory (contains `/` or starts
# with `.worktrees/`) and is not a remote ref like origin/main.
WORKTREE_PATH=""
for token in $COMMAND; do
  case "$token" in
    git|worktree|add|-*) continue ;;
    origin/*|main|master) continue ;;
  esac
  if [[ "$token" == */* || "$token" == ".worktrees/"* ]]; then
    WORKTREE_PATH="$token"
  fi
done

if [[ -z "$WORKTREE_PATH" ]]; then
  exit 0
fi

# Resolve source dir. Prefer the command's cwd (where the user invoked the
# command). If cwd is empty or unreadable, fall back to the directory
# holding this hook's parent (i.e. the project root or worktree root).
SOURCE_DIR=""
if [[ -n "$CWD" && -d "$CWD" ]]; then
  SOURCE_DIR="$CWD"
elif [[ -n "${CLAUDE_PROJECT_DIR:-}" && -d "$CLAUDE_PROJECT_DIR" ]]; then
  SOURCE_DIR="$CLAUDE_PROJECT_DIR"
else
  SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# Resolve the destination worktree as an absolute path. If the user typed
# a relative path, anchor to the source dir (the typical pattern).
if [[ "$WORKTREE_PATH" != /* ]]; then
  WORKTREE_PATH="$SOURCE_DIR/$WORKTREE_PATH"
fi

if [[ ! -d "$WORKTREE_PATH" ]]; then
  # Worktree creation may have failed; bail silently — the dev-kit
  # worktree-guard surfaces the real failure.
  exit 0
fi

copied=0
for name in .env.local .env.staging; do
  src="$SOURCE_DIR/$name"
  dst="$WORKTREE_PATH/$name"
  if [[ ! -f "$src" ]]; then
    continue
  fi
  if [[ -f "$dst" ]]; then
    continue
  fi
  if cp -p "$src" "$dst" 2>/dev/null; then
    copied=$((copied + 1))
  fi
done

if [[ "$copied" -gt 0 ]]; then
  relative="${WORKTREE_PATH#$SOURCE_DIR/}"
  printf 'post-worktree-add: copied %d env file(s) to %s\n' "$copied" "$relative" >&2
fi

exit 0
