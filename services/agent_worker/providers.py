"""Provider-neutral HTTP model adapters with bounded output and redaction-safe errors."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .runtime import ModelResult


class AgentProviderError(RuntimeError):
    """A provider failure safe to expose as a generic run failure."""


JsonRequest = Callable[
    [str, str, Mapping[str, str], Mapping[str, object], float], dict[str, Any]
]


def _request_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    timeout: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **dict(headers)},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise AgentProviderError(f"model provider returned HTTP {exc.code}") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, URLError):
        raise AgentProviderError("model provider request failed") from None
    if not isinstance(value, dict):
        raise AgentProviderError("model provider response is invalid")
    return value


class DeterministicAgentModel:
    provider_id = "local"

    def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
        message = prompt.strip() or "(empty message)"
        return ModelResult(output=f"Local echo: {message}", usage_units=1)


class HttpAgentModel:
    provider_id: str

    def __init__(
        self,
        *,
        provider_id: str,
        model: str,
        api_key: str,
        base_url: str,
        max_output_tokens: int,
        request_json: JsonRequest = _request_json,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_output_tokens = max_output_tokens
        self._request_json = request_json

    def __call__(self, prompt: str, *, idempotency_key: str, timeout_seconds: float) -> ModelResult:
        if self.provider_id == "openai":
            return self._openai(prompt, timeout_seconds)
        if self.provider_id == "anthropic":
            return self._anthropic(prompt, timeout_seconds)
        if self.provider_id == "gemini":
            return self._gemini(prompt, timeout_seconds)
        raise AgentProviderError("unsupported model provider")

    def _openai(self, prompt: str, timeout: float) -> ModelResult:
        value = self._request_json(
            "POST",
            f"{self._base_url}/chat/completions",
            {"Authorization": f"Bearer {self._api_key}"},
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self._max_output_tokens,
            },
            timeout,
        )
        choices = value.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AgentProviderError("OpenAI response has no choices")
        message = choices[0].get("message")
        output = message.get("content") if isinstance(message, dict) else None
        usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
        return self._result(output, usage.get("total_tokens"))

    def _anthropic(self, prompt: str, timeout: float) -> ModelResult:
        value = self._request_json(
            "POST",
            f"{self._base_url}/messages",
            {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": self._max_output_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout,
        )
        content = value.get("content")
        output = content[0].get("text") if isinstance(content, list) and content and isinstance(content[0], dict) else None
        usage = value.get("usage") if isinstance(value.get("usage"), dict) else {}
        total = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        return self._result(output, total)

    def _gemini(self, prompt: str, timeout: float) -> ModelResult:
        value = self._request_json(
            "POST",
            f"{self._base_url}/v1beta/models/{self.model}:generateContent?key={self._api_key}",
            {},
            {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": self._max_output_tokens}},
            timeout,
        )
        candidates = value.get("candidates")
        candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        output = parts[0].get("text") if isinstance(parts, list) and parts and isinstance(parts[0], dict) else None
        usage = value.get("usageMetadata") if isinstance(value.get("usageMetadata"), dict) else {}
        return self._result(output, usage.get("totalTokenCount"))

    @staticmethod
    def _result(output: object, usage: object) -> ModelResult:
        if not isinstance(output, str) or not output.strip():
            raise AgentProviderError("model provider returned empty content")
        try:
            units = max(1, int(usage))
        except (TypeError, ValueError):
            units = 1
        return ModelResult(output=output, usage_units=units)


def build_agent_model(
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
    max_output_tokens: int,
) -> DeterministicAgentModel | HttpAgentModel:
    if provider == "local":
        return DeterministicAgentModel()
    defaults = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com",
    }
    return HttpAgentModel(
        provider_id=provider,
        model=model,
        api_key=api_key,
        base_url=base_url or defaults[provider],
        max_output_tokens=max_output_tokens,
    )
