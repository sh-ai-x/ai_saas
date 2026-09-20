"""Deterministic, allowlisted repository index used by the project pack."""

from __future__ import annotations

import hashlib
import re
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
    def __init__(self, root: str | Path, *, allowlisted_paths: tuple[str, ...] = ("agent_platform", "services", "project_packs", "tests")) -> None:
        self.root = Path(root).resolve()
        self.allowlisted_paths = tuple(path.strip("/") for path in allowlisted_paths)
        self._files: dict[str, IndexedFile] = {}

    def build(self) -> "RepositoryIndex":
        self._files = {}
        for candidate in sorted(self.root.rglob("*")):
            if not candidate.is_file() or any(part.startswith(".") for part in candidate.relative_to(self.root).parts):
                continue
            relative = candidate.relative_to(self.root).as_posix()
            if not self.is_authorized(relative) or candidate.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".json", ".md", ".yaml", ".yml"}:
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            symbols = tuple(sorted(set(re.findall(r"(?:def|class|function|const|interface)\s+([A-Za-z_][A-Za-z0-9_]*)", content))))
            self._files[relative] = IndexedFile(relative, content, hashlib.sha256(content.encode()).hexdigest(), tuple(content.splitlines()), symbols)
        return self

    def is_authorized(self, path: str) -> bool:
        normalized = Path(path).as_posix()
        if normalized.startswith("../") or normalized.startswith("/"):
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

