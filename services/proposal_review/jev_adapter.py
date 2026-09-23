"""Optional single-batch JEV context filter and evaluator boundary."""

from __future__ import annotations

import os
import json
from contextvars import ContextVar
from urllib.request import Request, urlopen
from typing import Any, Callable, Mapping


class JEVReviewAdapter:
    def __init__(self, evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None) -> None:
        self.evaluator = evaluator
        self._calls: ContextVar[int] = ContextVar("jev_review_calls", default=0)

    @property
    def calls(self) -> int:
        return self._calls.get()

    def begin_review(self) -> None:
        """Start an independent one-call budget for the current request context."""
        self._calls.set(0)

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> "JEVReviewAdapter":
        values = {**os.environ, **(environment or {})}
        # The adapter remains opt-in until the deployed JEV contract is configured.
        if values.get("JEV_REVIEW_ENABLED", "").lower() not in {"1", "true", "yes"} or not values.get("JEV_API_KEY") or not values.get("JEV_API_URL"):
            return cls()
        api_url = values["JEV_API_URL"]
        api_key = values["JEV_API_KEY"]

        def remote(report: Mapping[str, Any]) -> Mapping[str, Any]:
            request = Request(api_url, data=json.dumps(dict(report), default=str).encode("utf-8"), method="POST", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            with urlopen(request, timeout=8) as response:  # noqa: S310 - URL is explicit operator configuration
                value = json.loads(response.read(256_000))
            if not isinstance(value, Mapping):
                raise ValueError("JEV response must be an object")
            return value

        return cls(remote)

    def evaluate(self, report: Mapping[str, Any]) -> dict[str, Any]:
        """Keep the legacy rubric evaluation seam for direct callers."""
        result = self._invoke(report)
        return self._result(result)

    def filter_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        """Use the single JEV call to select evidence before synthesis.

        The caller sends compact evidence candidates, never raw repository
        content. A provider that does not return selections leaves the
        deterministic candidates unchanged.
        """
        result = self._invoke({"mode": "context_filter", **dict(context)})
        selected = result.get("selected_evidence_ids", result.get("selected_ids", []))
        if not isinstance(selected, list):
            selected = []
        return {**self._result(result), "selected_evidence_ids": [str(item) for item in selected[:80]]}

    def _invoke(self, report: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.evaluator is None:
            return {"status": "skipped", "reason": "JEV review is disabled", "score": None}
        if self.calls >= 1:
            raise RuntimeError("JEV review budget exhausted")
        self._calls.set(self.calls + 1)
        result = self.evaluator(report)
        if not isinstance(result, Mapping):
            raise ValueError("JEV result must be an object")
        return result

    @staticmethod
    def _result(result: Mapping[str, Any]) -> dict[str, Any]:
        return {"status": str(result.get("status", "completed")), "score": result.get("score"), "rubric": dict(result.get("rubric", {}))}
