"""Explicit structured-model boundary with a no-network fake provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

try:
    from typing_extensions import TypedDict
except ImportError:  # pragma: no cover - Python 3.12 has the fallback
    from typing import TypedDict

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
    """Adapter for a real LangChain runnable; it never owns product policy."""

    provider_id = "langchain"

    def __init__(self, runnable: Any, *, input_builder: Callable[..., Any] | None = None) -> None:
        if not callable(getattr(runnable, "invoke", None)):
            raise TypeError("LangChain adapter requires an object with invoke")
        self._runnable = runnable
        self._input_builder = input_builder

    def generate(self, prompt: str, *, context: Mapping[str, Any], schema: str, idempotency_key: str) -> StructuredModelResult:
        payload = {"prompt": prompt, "context": context, "schema": schema, "idempotency_key": idempotency_key}
        value = self._runnable.invoke(self._input_builder(**payload) if self._input_builder else payload)
        data = _mapping_from_result(value)
        input_tokens, output_tokens = _usage_from_result(value)
        estimated = input_tokens is None or output_tokens is None
        return StructuredModelResult(data, input_tokens or estimate_tokens(prompt), output_tokens or estimate_tokens(json.dumps(data, default=str)), estimated)


class ProposalAnalysis(TypedDict):
    summary: str
    requirement_ids: list[str]
    claims: list[str]


def build_langchain_proposal_adapter(chat_model: Any) -> LangChainStructuredModelAdapter:
    """Build a typed LangChain prompt/runnable without importing a provider SDK.

    The caller supplies a configured LangChain chat model (OpenAI, Anthropic,
    a local gateway, or a test runnable). Provider credentials therefore stay
    outside this product package, while structured output remains explicit.
    """

    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError as exc:  # pragma: no cover - exercised in minimal envs
        raise RuntimeError("langchain-core is required for the LangChain runtime") from exc
    structured = getattr(chat_model, "with_structured_output", None)
    if not callable(structured):
        raise TypeError("chat model must expose with_structured_output")
    chain = ChatPromptTemplate.from_messages(
        [
            ("system", "Analyze the proposal using only the supplied repository evidence. Return the requested schema."),
            ("human", "Proposal:\n{proposal}\nEvidence context:\n{context}"),
        ]
    ) | structured(ProposalAnalysis)

    def input_builder(**payload: Any) -> Mapping[str, Any]:
        return {"proposal": payload["prompt"], "context": json.dumps(payload["context"], sort_keys=True)}

    return LangChainStructuredModelAdapter(chain, input_builder=input_builder)


def build_openai_proposal_adapter(*, model_name: str | None = None, temperature: float = 0.0) -> LangChainStructuredModelAdapter:
    """Create the production OpenAI path without importing it in Local Lite."""

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install the langchain optional extra for AGENT_PROVIDER_MODE=langchain") from exc
    model = ChatOpenAI(model=model_name or "gpt-4o-mini", temperature=temperature)
    return build_langchain_proposal_adapter(model)


def _mapping_from_result(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        data = value.get("data", value)
        if isinstance(data, Mapping):
            return data
    for method_name in ("model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            data = method()
            if isinstance(data, Mapping):
                return data
    raise ValueError("LangChain runnable must return a mapping or structured model")


def _usage_from_result(value: Any) -> tuple[int | None, int | None]:
    candidates: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        candidates.append(value)
        for key in ("usage", "token_usage", "response_metadata", "usage_metadata"):
            nested = value.get(key)
            if isinstance(nested, Mapping):
                candidates.append(nested)
    for attr in ("usage_metadata", "response_metadata"):
        nested = getattr(value, attr, None)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    input_tokens = output_tokens = None
    for candidate in candidates:
        input_tokens = input_tokens or _int_value(candidate, "input_tokens", "prompt_tokens")
        output_tokens = output_tokens or _int_value(candidate, "output_tokens", "completion_tokens")
    return input_tokens, output_tokens


def _int_value(value: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        if isinstance(value.get(key), int):
            return int(value[key])
    return None
