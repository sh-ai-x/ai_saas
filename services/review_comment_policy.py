"""Canonical comment fields used by review output and Ragas answers."""

from __future__ import annotations


_COMMENT_KEYS_BY_STATUS: dict[str, tuple[str, ...]] = {
    "implemented": ("implemented_comment",),
    "modified": ("implemented_comment", "changed_comment"),
    "partial": ("implemented_comment", "not_implemented_comment"),
    "missing": ("not_implemented_comment",),
    "unknown": ("not_implemented_comment",),
    "contradicted": ("not_implemented_comment", "changed_comment"),
}


def comment_keys_for_status(status: str) -> tuple[str, ...]:
    """Return the ordered explanation fields for one canonical review status."""
    return _COMMENT_KEYS_BY_STATUS.get(
        str(status).strip().lower(),
        ("implemented_comment", "not_implemented_comment", "changed_comment"),
    )
