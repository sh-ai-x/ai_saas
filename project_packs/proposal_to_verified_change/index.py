"""Deterministic, allowlisted repository index used by the project pack."""

from __future__ import annotations

import hashlib
import re
import os
from dataclasses import dataclass
from pathlib import Path


class UnauthorizedPath(PermissionError):
    pass


@dataclass(frozen=True)
class IndexedFile:
    path: str
    content: str
    content_hash: str
    lines: tuple[str, ...]
    symbols: tuple[str, ...]


class RepositoryIndex:
    def __init__(
        self,
        root: str | Path,
        *,
        allowlisted_paths: tuple[str, ...] = ("agent_platform", "services", "project_packs", "tests"),
        max_files: int = 2048,
        max_depth: int = 8,
    ) -> None:
        self.root = Path(root).resolve()
        self.allowlisted_paths = tuple(path.strip("/") for path in allowlisted_paths)
        self.max_files = max_files
        self.max_depth = max_depth
        self._files: dict[str, IndexedFile] = {}

    def build(self) -> "RepositoryIndex":
        self._files = {}
        for candidate in sorted(self.root.rglob("*")):
            relative_path = candidate.relative_to(self.root)
            if len(relative_path.parts) > self.max_depth or candidate.is_symlink() or not candidate.is_file() or any(part.startswith(".") for part in relative_path.parts):
                continue
            try:
                if not os.path.commonpath((str(self.root), str(candidate.resolve(strict=True)))) == str(self.root):
                    continue
            except OSError:
                continue
            relative = relative_path.as_posix()
            if not self.is_authorized(relative) or candidate.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".json", ".md", ".yaml", ".yml"}:
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            symbols = tuple(sorted(set(re.findall(r"(?:def|class|function|const|interface)\s+([A-Za-z_][A-Za-z0-9_]*)", content))))
            self._files[relative] = IndexedFile(relative, content, hashlib.sha256(content.encode()).hexdigest(), tuple(content.splitlines()), symbols)
            if len(self._files) >= self.max_files:
                break
        return self

    def refresh(self) -> "RepositoryIndex":
        """Re-read the bounded allowlist before a new analysis or hash check."""

        return self.build()

    def current_evidence(self, path: str, start_line: int = 1, end_line: int | None = None, symbol: str | None = None) -> tuple[int, int, str]:
        """Return a live hash, so a changed checkout cannot reuse old evidence."""

        del symbol
        if not self.is_authorized(path):
            raise UnauthorizedPath(path)
        normalized = Path(path).as_posix()
        candidate = (self.root / normalized).resolve(strict=True)
        if not os.path.commonpath((str(self.root), str(candidate))) == str(self.root) or not candidate.is_file() or candidate.is_symlink():
            raise UnauthorizedPath(path)
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FileNotFoundError(normalized) from exc
        lines = tuple(content.splitlines())
        end = len(lines) if end_line is None else end_line
        if start_line < 1 or end < start_line or end > len(lines):
            raise ValueError("line range is outside indexed file")
        selected = "\n".join(lines[start_line - 1 : end]).encode()
        return start_line, end, hashlib.sha256(selected).hexdigest()

    def is_authorized(self, path: str) -> bool:
        normalized = Path(path).as_posix()
        parts = Path(normalized).parts
        if normalized.startswith("/") or any(part in {"..", "."} for part in parts):
            return False
        return any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in self.allowlisted_paths)

    def files(self) -> tuple[IndexedFile, ...]:
        return tuple(self._files[key] for key in sorted(self._files))

    def get(self, path: str) -> IndexedFile:
        if not self.is_authorized(path):
            raise UnauthorizedPath(path)
        normalized = Path(path).as_posix()
        if normalized not in self._files:
            raise FileNotFoundError(normalized)
        return self._files[normalized]

    def evidence(self, path: str, start_line: int = 1, end_line: int | None = None, symbol: str | None = None) -> tuple[int, int, str]:
        file = self.get(path)
        end = len(file.lines) if end_line is None else end_line
        if start_line < 1 or end < start_line or end > len(file.lines):
            raise ValueError("line range is outside indexed file")
        selected = "\n".join(file.lines[start_line - 1 : end]).encode()
        return start_line, end, hashlib.sha256(selected).hexdigest()
