from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_javascript_toolchain_is_pnpm_workspace() -> None:
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    web_package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))

    assert root_package["packageManager"] == "pnpm@10.18.0"
    assert web_package["packageManager"] == "pnpm@10.18.0"
    assert (ROOT / "pnpm-workspace.yaml").exists()
    assert (ROOT / "pnpm-lock.yaml").exists()
    assert not (ROOT / "package-lock.json").exists()
    assert not (ROOT / "apps/web/package-lock.json").exists()
    web_dockerfile = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    assert "npm ci" not in web_dockerfile
    assert "npm run" not in web_dockerfile


def test_python_toolchain_is_uv_locked() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    test_script = (ROOT / "scripts/test.sh").read_text(encoding="utf-8")
    verify_script = (ROOT / "scripts/verify-local.sh").read_text(encoding="utf-8")

    assert "pytest>=8.0,<9.0" in pyproject
    assert (ROOT / "uv.lock").exists()
    assert "uv sync --locked" in test_script
    assert "uv run --locked pytest" in test_script
    assert "pip install" not in test_script
    assert "uv run --locked" in verify_script


def test_container_entrypoints_use_the_locked_toolchains() -> None:
    python_dockerfiles = (
        ROOT / "docker/dev/Dockerfile",
        ROOT / "docker/prod/foundation.Dockerfile",
    )
    for dockerfile in python_dockerfiles:
        content = dockerfile.read_text(encoding="utf-8")
        assert "astral-sh/uv" in content
        assert "uv sync" in content
        assert '"uv", "run"' in content

    compose = (ROOT / "docker/prod/compose.yaml").read_text(encoding="utf-8")
    assert '"pnpm", "--filter", "ai-saas-foundation-web", "db:migrate"' in compose
