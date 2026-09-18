"""Small dependency-free OpenTelemetry-shaped tracer with privacy controls.

The foundation keeps the exporter boundary optional so the free profile can
sample into a bounded local exporter. Applications may adapt ``SpanExporter``
to an OTLP exporter without changing run or billing code.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol


_SENSITIVE_KEY_PARTS = (
    "prompt",
    "input",
    "payment",
    "payload",
    "authorization",
    "oauth",
    "code",
    "token",
    "secret",
    "password",
    "credential",
    "cookie",
    "api_key",
    "apikey",
    "raw_body",
)
_SECRET_PATTERNS = (
    (re.compile(r"(?i)sk-[A-Za-z0-9_-]+"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)card(?:_number)?[=:]\s*\d+"), "card=[REDACTED]"),
)


def _redact_string(value: str) -> str:
    result = value
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Return attributes safe for a trace exporter.

    Sensitive fields are retained only as a marker; raw prompt, OAuth, and
    payment values never cross the exporter boundary.
    """

    def clean(key: str, value: Any) -> Any:
        normalized = key.lower().replace("-", "_")
        if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
            return "[REDACTED]"
        if isinstance(value, str):
            return _redact_string(value)
        if isinstance(value, Mapping):
            return {str(child_key): clean(str(child_key), child_value) for child_key, child_value in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(key, child) for child in value]
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        return str(value)

    return {str(key): clean(str(key), value) for key, value in attributes.items()}


class SpanExporter(Protocol):
    def export(self, span: Mapping[str, Any]) -> None:
        ...


class InMemorySpanExporter:
    """Bounded test/local exporter; it never writes request data to logs."""

    def __init__(self, max_spans: int = 1024) -> None:
        if not isinstance(max_spans, int) or isinstance(max_spans, bool) or max_spans <= 0:
            raise ValueError("max_spans must be a positive integer")
        self._max_spans = max_spans
        self._spans: list[dict[str, Any]] = []

    @property
    def spans(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(span) for span in self._spans)

    def export(self, span: Mapping[str, Any]) -> None:
        if len(self._spans) >= self._max_spans:
            self._spans.pop(0)
        self._spans.append(dict(span))


@dataclass
class _Span:
    tracer: "SampledTracer"
    name: str
    trace_id: str
    span_id: str
    attributes: dict[str, Any]
    sampled: bool
    started_at: float
    status: str = "ok"

    def __enter__(self) -> "_Span":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None:
            self.status = "error"
            self.attributes["error.type"] = getattr(exc_type, "__name__", "exception")
        self.tracer._finish(self)

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes.update(redact_attributes({key: value}))


class SampledTracer:
    """Sample spans before export and redact attributes at both write points."""

    def __init__(
        self,
        *,
        sample_rate: float = 0.1,
        exporter: SpanExporter | None = None,
        random_value: Callable[[], float] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(sample_rate, bool) or not 0.0 <= sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0 and 1")
        self.sample_rate = float(sample_rate)
        self.exporter = exporter
        self._random_value = random_value or __import__("random").random
        self._clock = clock

    def start_span(self, name: str, attributes: Mapping[str, Any] | None = None) -> _Span:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("span name must be non-empty")
        sampled = self.sample_rate == 1.0 or (
            self.sample_rate > 0.0 and self._random_value() < self.sample_rate
        )
        return _Span(
            self,
            name.strip(),
            uuid.uuid4().hex,
            uuid.uuid4().hex[:16],
            redact_attributes(attributes or {}),
            sampled,
            self._clock(),
        )

    def _finish(self, span: _Span) -> None:
        if not span.sampled or self.exporter is None:
            return
        document = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "name": span.name,
            "status": span.status,
            "duration_ms": round(max(0.0, self._clock() - span.started_at) * 1000, 3),
            "attributes": redact_attributes(span.attributes),
        }
        try:
            self.exporter.export(document)
        except Exception:
            # Telemetry loss must never block durable run state or billing.
            return


SampledOpenTelemetry = SampledTracer
