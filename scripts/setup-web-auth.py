#!/usr/bin/env python3
"""Prepare the web app for a real Google OAuth + Neon + Drizzle run."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NEON_PROJECT_ID = "lucky-boat-01406333"
DEFAULT_NEON_BRANCH = "production"
DEFAULT_WEB_ENV = Path("apps/web/.env.local")
DEFAULT_NEON_ENV = Path(".env.local")
ENV_KEY = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:@?&=+,%~-]+$")


def resolve_path(root: Path, value: str | None, default: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else root / path


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        match = ENV_KEY.match(stripped)
        if not match:
            continue
        key = match.group(1)
        value = stripped[stripped.find("=") + 1 :].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def format_dotenv_value(value: str) -> str:
    if value and SAFE_VALUE.fullmatch(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_dotenv(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    seen: set[str] = set()
    rendered: list[str] = []

    for line in lines:
        match = ENV_KEY.match(line.strip())
        if match and match.group(1) in updates:
            key = match.group(1)
            rendered.append(f"{key}={format_dotenv_value(updates[key])}\n")
            seen.add(key)
        else:
            rendered.append(line)

    if rendered and not rendered[-1].endswith("\n"):
        rendered[-1] += "\n"
    if rendered and rendered[-1].strip():
        rendered.append("\n")
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={format_dotenv_value(value)}\n")

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write("".join(rendered))
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def run_command(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode:
        raise RuntimeError(f"command failed with exit code {result.returncode}: {command[0]}")


def generate_secret() -> str:
    openssl = shutil.which("openssl")
    if openssl:
        result = subprocess.run(
            [openssl, "rand", "-base64", "32"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    return secrets.token_urlsafe(32)


def build_parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Configure apps/web/.env.local for Neon, Better Auth, Google OAuth, and Drizzle."
    )
    command.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    command.add_argument("--env-file", help="web dotenv path, relative to the repository root")
    command.add_argument("--neon-env-file", help="dotenv path written by neon link")
    command.add_argument("--app-env", choices=("local", "test", "staging", "production"), default="staging")
    command.add_argument("--auth-url", default="http://localhost:3000")
    command.add_argument("--link-neon", action="store_true", help="link the configured Neon branch before importing its URL")
    command.add_argument("--neon-project-id", default=DEFAULT_NEON_PROJECT_ID)
    command.add_argument("--neon-branch", default=DEFAULT_NEON_BRANCH)
    command.add_argument("--migrate", action="store_true", help="apply the committed Drizzle migrations after writing env")
    return command


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    args = build_parser().parse_args(argv)
    root = args.repo_root.resolve()
    web_env = resolve_path(root, args.env_file, DEFAULT_WEB_ENV)
    neon_env = resolve_path(root, args.neon_env_file, DEFAULT_NEON_ENV)

    try:
        if args.link_neon:
            neon = shutil.which("neon")
            if not neon:
                raise RuntimeError("neon CLI was not found; install it with `pnpm add --global neon@latest`")
            run_command(
                [
                    neon,
                    "link",
                    "--project-id",
                    args.neon_project_id,
                    "--branch",
                    args.neon_branch,
                    "-y",
                ],
                cwd=root,
            )

        target = parse_dotenv(web_env)
        source = parse_dotenv(neon_env)
        merged = {key: value for key, value in source.items() if value.strip()}
        merged.update({key: value for key, value in target.items() if value.strip()})
        if not merged.get("DATABASE_URL") and merged.get("WEB_DATABASE_URL"):
            merged["DATABASE_URL"] = merged["WEB_DATABASE_URL"]

        secret = merged.get("BETTER_AUTH_SECRET") or generate_secret()
        updates = {
            "APP_ENV": args.app_env,
            "DATABASE_URL": merged.get("DATABASE_URL", ""),
            "BETTER_AUTH_URL": target.get("BETTER_AUTH_URL") or args.auth_url,
            "BETTER_AUTH_SECRET": secret,
            "APP_BASE_URL": target.get("APP_BASE_URL") or args.auth_url,
        }
        if merged.get("DATABASE_URL_UNPOOLED"):
            updates["DATABASE_URL_UNPOOLED"] = merged["DATABASE_URL_UNPOOLED"]
        if target.get("GOOGLE_CLIENT_ID"):
            updates["GOOGLE_CLIENT_ID"] = target["GOOGLE_CLIENT_ID"]
        if target.get("GOOGLE_CLIENT_SECRET"):
            updates["GOOGLE_CLIENT_SECRET"] = target["GOOGLE_CLIENT_SECRET"]

        required = ("DATABASE_URL", "BETTER_AUTH_SECRET", "BETTER_AUTH_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
        missing = [key for key in required if not updates.get(key, "").strip()]
        if missing:
            raise RuntimeError(
                "missing required values: "
                + ", ".join(missing)
                + ". Keep Google values in apps/web/.env.local and run Neon link first for DATABASE_URL."
            )

        updates["NEXT_PUBLIC_GOOGLE_AUTH_ENABLED"] = "true"
        write_dotenv(web_env, updates)

        migrate_env = os.environ.copy()
        migrate_env.update(updates)
        display_path = web_env.relative_to(root) if web_env.is_relative_to(root) else web_env
        print(f"Configured {display_path}")
        print("- Neon DATABASE_URL: present (value hidden)")
        print("- Better Auth secret: reused or generated (value hidden)")
        print("- Google OAuth: client ID and secret present (values hidden)")
        print(f"- APP_ENV: {args.app_env}")

        if args.migrate:
            pnpm = shutil.which("pnpm")
            if not pnpm:
                raise RuntimeError("pnpm was not found; install pnpm before running --migrate")
            run_command([pnpm, "--filter", "ai-saas-foundation-web", "db:migrate"], cwd=root, env=migrate_env)
            print("- Drizzle migration: applied")
        else:
            print("- Drizzle migration: skipped (rerun with --migrate to apply)")
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"setup-web-auth: ERROR: {error}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
