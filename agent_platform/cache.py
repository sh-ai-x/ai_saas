"""Content-addressed, deterministic context cache."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .redaction import redact


@dataclass(frozen=True)
class CacheLookup:
    key: str
    value: Mapping[str, Any]
    hit: bool


class ContentAddressedContextCache:
    def __init__(self) -> None:
        self._values: dict[str, Mapping[str, Any]] = {}

    @staticmethod
    def key_for(context: Mapping[str, Any]) -> str:
        encoded = json.dumps(redact(context), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get_or_put(self, context: Mapping[str, Any]) -> CacheLookup:
        key = self.key_for(context)
        if key in self._values:
            return CacheLookup(key, self._values[key], True)
        safe = redact(context)
        self._values[key] = safe
        return CacheLookup(key, safe, False)
