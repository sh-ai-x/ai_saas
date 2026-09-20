"""Explicit structured-model boundary with a no-network fake provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from agent_platform.budgets import estimate_tokens
from agent_platform.redaction import redact


@dataclass(frozen=True)
class StructuredModelResult:
    data: Mapping[str, Any]
    input_tokens: int
    output_tokens: int
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class StructuredModelPort(Protocol):
    provider_id: str

    def generate(self, prompt: str, *, context: Mapping[str, Any], schema: str, idempotency_key: str) -> StructuredModelResult: ...


class PromptContextAdapter:
    """Builds bounded, redacted context; auth and billing remain outside this adapter."""

    def build(self, proposal: str, context: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
        safe_context = redact(context)
        prompt = json.dumps({"task": "analyze proposal", "proposal": proposal, "context": safe_context}, sort_keys=True)
        return prompt, safe_context


class FakeStructuredModel:
    provider_id = "fake-local"

    def __init__(self, *, output_tokens: int = 32, estimated_usage: bool = False) -> None:
        self.output_tokens = output_tokens
        self.estimated_usage = estimated_usage
        self.calls: list[str] = []

    def generate(self, prompt: str, *, context: Mapping[str, Any], schema: str, idempotency_key: str) -> StructuredModelResult:
        del schema, idempotency_key
        self.calls.append(prompt)
        requirement_ids = tuple(str(value) for value in context.get("requirement_ids", ()))
        data = {"summary": "deterministic analysis", "requirement_ids": requirement_ids, "claims": ["evidence-backed"]}
        input_tokens = estimate_tokens(prompt)
        return StructuredModelResult(data, input_tokens, self.output_tokens, self.estimated_usage)


class LangChainStructuredModelAdapter:
    """Typed seam for an injected LangChain runnable; it never owns policy."""

    provider_id = "langchain"

    def __init__(self, runnable: Any) -> None:
        if not callable(getattr(runnable, "invoke", None)):
            raise TypeError("LangChain adapter requires an object with invoke")
        self._runnable = runnable

    def generate(self, prompt: str, *, context: Mapping[str, Any], schema: str, idempotency_key: str) -> StructuredModelResult:
        value = self._runnable.invoke({"prompt": prompt, "context": context, "schema": schema, "idempotency_key": idempotency_key})
        if not isinstance(value, Mapping):
            raise ValueError("LangChain runnable must return a mapping")
        data = value.get("data", value)
        if not isinstance(data, Mapping):
            raise ValueError("structured model data must be a mapping")
        input_tokens = value.get("input_tokens")
        output_tokens = value.get("output_tokens")
        estimated = not isinstance(input_tokens, int) or not isinstance(output_tokens, int)
        return StructuredModelResult(data, int(input_tokens) if isinstance(input_tokens, int) else estimate_tokens(prompt), int(output_tokens) if isinstance(output_tokens, int) else estimate_tokens(json.dumps(data, default=str)), estimated)

