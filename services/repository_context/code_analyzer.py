"""Deterministic source structure analysis; no source execution."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable

from .git_manifest import ManifestFile, RepositoryManifest


@dataclass(frozen=True)
class CodeContext:
    files: tuple[dict[str, object], ...]
    symbols: tuple[dict[str, object], ...]
    imports: tuple[dict[str, object], ...]
    candidates: tuple[dict[str, object], ...]
    unknowns: tuple[dict[str, str], ...]

    def public(self) -> dict[str, object]:
        return {"files": self.files, "symbols": self.symbols, "imports": self.imports, "candidates": self.candidates, "unknowns": self.unknowns}


_IMPORT_RE = re.compile(r"^\s*(?:import\s+([\w.@/-]+)|from\s+([\w.@/-]+)\s+import|(?:const|let|var)\s+.*?from\s+[\"']([^\"']+))", re.M)
_SYMBOL_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|def|interface|type|const)\s+([A-Za-z_$][\w$]*)", re.M)
_CANDIDATE_TERMS = ("prompt", "model", "retriev", "embedding", "langchain", "langgraph", "provider", "agent", "graph", "chain", "tool")


def _python_symbols(text: str) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    result: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result.append((node.name, int(getattr(node, "lineno", 1))))
    return result


def _symbols(item: ManifestFile) -> list[tuple[str, int]]:
    if item.language == "python":
        return _python_symbols(item.content)
    return [(match.group(1), item.content[: match.start()].count("\n") + 1) for match in _SYMBOL_RE.finditer(item.content)]


def analyze_manifest(manifest: RepositoryManifest) -> CodeContext:
    files: list[dict[str, object]] = []
    symbols: list[dict[str, object]] = []
    imports: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    unknowns: list[dict[str, str]] = []
    for item in manifest.files:
        files.append({"path": item.path, "language": item.language, "size": item.size, "sha256": item.sha256})
        found_symbols = _symbols(item)
        for name, line in found_symbols:
            symbols.append({"path": item.path, "name": name, "line": line, "language": item.language})
        for match in _IMPORT_RE.finditer(item.content):
            module = next((group for group in match.groups() if group), None)
            if module:
                imports.append({"path": item.path, "module": module, "line": item.content[: match.start()].count("\n") + 1})
        lower = item.content.lower()
        matched = [term for term in _CANDIDATE_TERMS if term in lower or term in item.path.lower()]
        if matched:
            candidates.append({"path": item.path, "signals": matched[:6], "symbols": [name for name, _ in found_symbols[:12]]})
        elif item.language not in {"markdown", "text", "json", "yaml", "html", "css"} and not found_symbols:
            unknowns.append({"path": item.path, "reason": "parser produced no symbols"})
    return CodeContext(tuple(files), tuple(symbols), tuple(imports), tuple(candidates), tuple(unknowns))
