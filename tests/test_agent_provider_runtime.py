from __future__ import annotations

import unittest

from services.agent_worker.providers import HttpAgentModel


class AgentProviderRuntimeTests(unittest.TestCase):
    def test_openai_usage_and_content_are_normalized(self) -> None:
        def request(method, url, headers, payload, timeout):
            self.assertEqual(headers["Authorization"], "Bearer secret")
            return {"choices": [{"message": {"content": "answer"}}], "usage": {"total_tokens": 7}}

        result = HttpAgentModel(provider_id="openai", model="gpt-test", api_key="secret", base_url="https://example.test/v1", max_output_tokens=32, request_json=request)("hello", idempotency_key="key", timeout_seconds=3)
        self.assertEqual(result.output, "answer")
        self.assertEqual(result.usage_units, 7)

    def test_anthropic_and_gemini_shapes_are_supported(self) -> None:
        def anthropic(method, url, headers, payload, timeout):
            return {"content": [{"text": "anthropic answer"}], "usage": {"input_tokens": 2, "output_tokens": 3}}

        def gemini(method, url, headers, payload, timeout):
            return {"candidates": [{"content": {"parts": [{"text": "gemini answer"}]}}], "usageMetadata": {"totalTokenCount": 5}}

        anthropic_result = HttpAgentModel(provider_id="anthropic", model="claude-test", api_key="secret", base_url="https://example.test/v1", max_output_tokens=32, request_json=anthropic)("hello", idempotency_key="key", timeout_seconds=3)
        gemini_result = HttpAgentModel(provider_id="gemini", model="gemini-test", api_key="secret", base_url="https://example.test", max_output_tokens=32, request_json=gemini)("hello", idempotency_key="key", timeout_seconds=3)
        self.assertEqual(anthropic_result.usage_units, 5)
        self.assertEqual(gemini_result.output, "gemini answer")

    def test_empty_provider_content_fails_closed(self) -> None:
        def request(method, url, headers, payload, timeout):
            return {"choices": [{"message": {"content": ""}}]}

        with self.assertRaises(RuntimeError):
            HttpAgentModel(provider_id="openai", model="gpt-test", api_key="secret", base_url="https://example.test/v1", max_output_tokens=32, request_json=request)("hello", idempotency_key="key", timeout_seconds=3)


if __name__ == "__main__":
    unittest.main()
