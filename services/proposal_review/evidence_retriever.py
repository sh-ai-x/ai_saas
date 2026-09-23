"""Top-k deterministic evidence selection; no model calls."""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.repository_context.code_analyzer import CodeContext
from services.repository_context.git_manifest import RepositoryManifest
from .requirements import Requirement


@dataclass(frozen=True)
class Evidence:
    requirement_id: str
    path: str
    line: int
    excerpt: str
    score: int
    reason: str

    def public(self) -> dict[str, object]:
        return self.__dict__.copy()


def retrieve_evidence(requirement: Requirement, manifest: RepositoryManifest, code: CodeContext, *, limit: int = 5) -> tuple[Evidence, ...]:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", requirement.text) if token.lower() not in {"the", "and", "with", "must", "should", "from", "that"}}
    scored: list[Evidence] = []
    for item in manifest.files:
        lower_path = item.path.lower()
        for index, raw_line in enumerate(item.content.splitlines(), start=1):
            lower_line = raw_line.lower()
            overlap = sum(1 for token in tokens if token in lower_line or token in lower_path)
            signal = sum(1 for term in ("prompt", "model", "retriev", "graph", "provider", "trace", "safety", "cost") if term in lower_line)
            score = overlap * 3 + signal
            if score <= 0:
                continue
            excerpt = " ".join(raw_line.strip().split())[:240]
            scored.append(Evidence(requirement.requirement_id, item.path, index, excerpt, score, "token+AI-signal overlap"))
    scored.sort(key=lambda item: (-item.score, item.path, item.line))
    return tuple(scored[:limit])
