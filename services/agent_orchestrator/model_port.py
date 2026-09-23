"""Explicit structured-model boundary with a no-network fake provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

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

    def __init__(
        self,
        runnable: Any,
        *,
        input_builder: Callable[..., Any] | None = None,
        result_validator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        if not callable(getattr(runnable, "invoke", None)):
            raise TypeError("LangChain adapter requires an object with invoke")
        self._runnable = runnable
        self._input_builder = input_builder
        self._result_validator = result_validator

    def generate(self, prompt: str, *, context: Mapping[str, Any], schema: str, idempotency_key: str) -> StructuredModelResult:
        payload = {"prompt": prompt, "context": context, "schema": schema, "idempotency_key": idempotency_key}
        value = self._runnable.invoke(self._input_builder(**payload) if self._input_builder else payload)
        data = _mapping_from_result(value)
        if self._result_validator is not None:
            data = self._result_validator(data)
        input_tokens, output_tokens = _usage_from_result(value)
        estimated = input_tokens is None or output_tokens is None
        return StructuredModelResult(
            data,
            input_tokens if input_tokens is not None else estimate_tokens(prompt),
            output_tokens if output_tokens is not None else estimate_tokens(json.dumps(data, default=str)),
            estimated,
        )


def _mapping_from_result(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        data = value.get("data", value)
        if isinstance(data, Mapping):
            return data
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        if isinstance(data, Mapping):
            return data
    raise ValueError("LangChain runnable must return a mapping")


def _usage_from_result(value: Any) -> tuple[int | None, int | None]:
    candidates: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        candidates.append(value)
        for key in ("usage_metadata", "response_metadata", "usage"):
            nested = value.get(key)
            if isinstance(nested, Mapping):
                candidates.append(nested)
    input_tokens = output_tokens = None
    for candidate in candidates:
        if input_tokens is None:
            input_tokens = _int_value(candidate, "input_tokens", "prompt_tokens")
        if output_tokens is None:
            output_tokens = _int_value(candidate, "output_tokens", "completion_tokens")
    return input_tokens, output_tokens


def _int_value(value: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return int(candidate)
    return None


def _validate_proposal_analysis(value: Mapping[str, Any]) -> Mapping[str, Any]:
    required = {"summary", "requirement_ids", "claims"}
    missing = sorted(required.difference(value))
    if missing or not isinstance(value.get("summary"), str):
        raise ValueError("LangChain result does not match proposal analysis schema")
    if not all(isinstance(value.get(field), list) and all(isinstance(item, str) for item in value[field]) for field in ("requirement_ids", "claims")):
        raise ValueError("LangChain result lists must contain strings")
    return {"summary": value["summary"], "requirement_ids": list(value["requirement_ids"]), "claims": list(value["claims"])}


def build_langchain_proposal_adapter(chat_model: Any) -> LangChainStructuredModelAdapter:
    chain = chat_model.with_structured_output(dict) if callable(getattr(chat_model, "with_structured_output", None)) else chat_model
    return LangChainStructuredModelAdapter(chain, result_validator=_validate_proposal_analysis)


def build_openai_proposal_adapter(*, model_name: str | None = None, temperature: float = 0.0) -> LangChainStructuredModelAdapter:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("langchain-openai is required for the OpenAI adapter") from exc
    model = ChatOpenAI(model=model_name or "gpt-4o-mini", temperature=temperature)
    return build_langchain_proposal_adapter(model)
