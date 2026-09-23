"""Deterministic requirement extraction from bounded proposal sections."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .document_parser import ProposalDocument


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    text: str
    source: str
    kind: str
    kind_code: str
    kind_label: str
    kind_description: str

    def public(self) -> dict[str, str]:
        return self.__dict__.copy()


_MARKER = re.compile(r"(?:^|\n)\s*(?:[-*]|\d+[.)])\s+(.{12,500})", re.M)
_KEYWORDS = re.compile(r"\b(must|should|required|shall|acceptance|requirement|goal|non-goal|latency|cost|safety|trace|checkpoint|test)\b", re.I)


def extract_requirements(document: ProposalDocument, *, max_items: int = 40) -> tuple[Requirement, ...]:
    result: list[Requirement] = []
    seen: set[str] = set()
    requirement_number = 0
    acceptance_number = 0
    for section in document.sections:
        candidates = _MARKER.findall(section.text) or [section.text]
        for text in candidates:
            normalized = " ".join(text.split())[:500]
            if len(normalized) < 12 or normalized.lower() in seen:
                continue
            if _KEYWORDS.search(normalized) or len(candidates) == 1:
                seen.add(normalized.lower())
                kind = "acceptance" if re.search(r"acceptance|must|required|shall", normalized, re.I) else "requirement"
                if kind == "acceptance":
                    acceptance_number += 1
                    requirement_id = f"AC-{acceptance_number:03d}"
                else:
                    requirement_number += 1
                    requirement_id = f"REQ-{requirement_number:03d}"
                kind_code = "AC" if kind == "acceptance" else "REQ"
                kind_label = "Acceptance Criteria" if kind_code == "AC" else "Requirement"
                kind_description = "Acceptance Criteria: a concrete and verifiable condition for deciding completion" if kind_code == "AC" else "Requirement: a functional, quality, or operational capability the system must provide or preserve"
                result.append(Requirement(requirement_id, normalized, section.source, kind, kind_code, kind_label, kind_description))
            if len(result) >= max_items:
                return tuple(result)
    return tuple(result)
