"""Filesystem artifact package for human merge/delivery review."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agent_platform.redaction import redact


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    path: str
    digest: str
    bytes_written: int


class ReviewArtifactStore:
    """Write redacted, immutable-by-convention review packages atomically."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, artifact_id: str, package: Mapping[str, Any]) -> Artifact:
        if not artifact_id or "/" in artifact_id or "\\" in artifact_id or artifact_id in {".", ".."}:
            raise ValueError("artifact_id must be a path-safe identifier")
        encoded = json.dumps(redact(package), sort_keys=True, default=str, indent=2).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        target = self.root / f"{artifact_id}-{digest[:16]}.json"
        fd, temporary = tempfile.mkstemp(prefix=f".{artifact_id}-", dir=self.root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return Artifact(artifact_id, str(target), digest, len(encoded))
