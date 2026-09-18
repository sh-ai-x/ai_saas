"""Inngest-compatible bounded worker handler."""

from __future__ import annotations

from typing import Mapping

from .runtime import BoundedWorker


class BoundedInngestWorkflow:
    """Validate an event envelope before handing it to the worker."""

    def __init__(self, worker: BoundedWorker, *, max_runtime_seconds: float = 300.0) -> None:
        if not 0 < max_runtime_seconds <= 900:
            raise ValueError("workflow runtime must be between 0 and 900 seconds")
        self._worker = worker
        self.max_runtime_seconds = max_runtime_seconds

    def handle(self, event: Mapping[str, object]):
        if event.get("name") != "run.requested":
            raise ValueError("unsupported workflow event")
        data = event.get("data")
        if not isinstance(data, Mapping) or not isinstance(data.get("run_id"), str):
            raise ValueError("run.requested must carry a run_id")
        return self._worker.execute(data["run_id"])
