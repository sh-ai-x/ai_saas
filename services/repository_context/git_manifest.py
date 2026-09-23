"""Git-aware, read-only repository manifest.

The manifest is intentionally an in-memory analysis boundary. It never copies a
repository and never executes repository-provided commands.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_FILE_BYTES = 256 * 1024
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024
SECRET_PATH = re.compile(r"(^|/)(\.env(?:\.|$)|.*\.(?:pem|key|p12|pfx|crt|cer|der)$|credentials?\b|secrets?\b)", re.I)
BUILD_PARTS = {".git", ".worktrees", "worktrees", "node_modules", ".next", "dist", "build", "coverage", "target", ".venv", "venv", "__pycache__", ".cache", ".turbo"}
TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".css", ".go", ".graphql", ".html", ".java", ".js", ".json", ".jsx",
    ".kt", ".md", ".mjs", ".py", ".rb", ".rs", ".sql", ".swift", ".toml", ".ts", ".tsx",
    ".txt", ".vue", ".xml", ".yaml", ".yml",
}


@dataclass(frozen=True)
class ManifestFile:
    path: str
    size: int
    sha256: str
    language: str
    content: str = field(repr=False, default="")

    def public(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256, "language": self.language}


@dataclass(frozen=True)
class RepositoryManifest:
    root: str
    branch: str | None
    head: str | None
    files: tuple[ManifestFile, ...]
    excluded: dict[str, int]
    fingerprint: str

    def public(self) -> dict[str, object]:
        return {
            "root_name": Path(self.root).name,
            "branch": self.branch,
            "head": self.head,
            "files": [item.public() for item in self.files],
            "excluded": dict(self.excluded),
            "fingerprint": self.fingerprint,
        }


def _run_git(root: Path, args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        timeout=3,
        text=False,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
        ".jsx": "javascript", ".mjs": "javascript", ".go": "go", ".rs": "rust",
        ".java": "java", ".kt": "kotlin", ".sql": "sql", ".md": "markdown",
        ".html": "html", ".css": "css", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    }.get(suffix, suffix.removeprefix(".") or "text")


def _excluded(path: str, data: bytes, *, max_file_bytes: int) -> str | None:
    parts = set(Path(path).parts)
    if SECRET_PATH.search(path):
        return "secret"
    if parts.intersection(BUILD_PARTS):
        return "build"
    if Path(path).suffix.lower() not in TEXT_EXTENSIONS:
        return "binary_or_unsupported"
    if len(data) > max_file_bytes:
        return "file_size"
    if b"\x00" in data:
        return "binary_or_unsupported"
    return None


def build_manifest(
    root: str | Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> RepositoryManifest:
    """Read only Git-visible source files under ``root``.

    ``--exclude-standard`` includes Git's info/exclude and global excludes in
    addition to the repository's .gitignore rules. Tracked files remain visible
    even when a later ignore rule would match them, which is Git's normal
    semantics and is important for reviewing committed source.
    """

    root_path = Path(root).expanduser().resolve(strict=True)
    if not root_path.is_dir():
        raise ValueError("repository root must be a directory")
    try:
        raw_paths = _run_git(root_path, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("repository must be a readable Git worktree") from exc
    paths = [item for item in raw_paths.split("\0") if item]
    excluded: dict[str, int] = {}
    files: list[ManifestFile] = []
    total_bytes = 0
    for relative in paths:
        if relative.startswith("/") or ".." in Path(relative).parts or relative == ".git" or relative.startswith(".git/"):
            excluded["unsafe_path"] = excluded.get("unsafe_path", 0) + 1
            continue
        candidate = root_path / relative
        if candidate.is_symlink():
            excluded["symlink"] = excluded.get("symlink", 0) + 1
            continue
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_path)
            data = candidate.read_bytes()
        except (OSError, ValueError):
            excluded["unreadable"] = excluded.get("unreadable", 0) + 1
            continue
        reason = _excluded(relative, data, max_file_bytes=max_file_bytes)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        if len(files) >= max_files:
            excluded["file_count"] = excluded.get("file_count", 0) + 1
            continue
        if total_bytes + len(data) > max_total_bytes:
            excluded["total_size"] = excluded.get("total_size", 0) + 1
            continue
        text = data.decode("utf-8", errors="replace")
        files.append(ManifestFile(relative, len(data), hashlib.sha256(data).hexdigest(), _language(relative), text))
        total_bytes += len(data)
    try:
        branch = _run_git(root_path, ["branch", "--show-current"]).strip() or None
        head = _run_git(root_path, ["rev-parse", "HEAD"]).strip() or None
    except (OSError, subprocess.SubprocessError):
        branch, head = None, None
    fingerprint_input = "\n".join(f"{item.path}:{item.sha256}" for item in files)
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    return RepositoryManifest(str(root_path), branch, head, tuple(files), excluded, fingerprint)
