"""Shared validation policy for repository evidence ranges."""

from __future__ import annotations

MAX_EVIDENCE_RANGE_LINES = 3


def is_valid_evidence_range(start_line: int, end_line: int) -> bool:
    """Return whether an evidence pointer contains one to three lines."""
    return (
        start_line >= 1
        and end_line >= start_line
        and end_line - start_line + 1 <= MAX_EVIDENCE_RANGE_LINES
    )
