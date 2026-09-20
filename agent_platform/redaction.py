"""Conservative redaction used at persistence and observability boundaries."""

from __future__ import annotations

import re
from typing import Any, Mapping

_PATTERNS = (
    (re.compile(r"(?i)\b(sk|pk)-[A-Za-z0-9_-]{8,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\b(?:authorization|password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;}]+"), "[REDACTED_CREDENTIAL]"),
    (re.compile(r"\b(?:card(?:_number)?|ssn)\s*[:=]\s*\d{4,}\b", re.IGNORECASE), "[REDACTED_SENSITIVE]"),
)


def redact_text(value: str) -> str:
    result = value
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): redact(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(child) for child in value]
    return value

