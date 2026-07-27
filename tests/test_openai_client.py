import os
import unittest
from unittest import mock

import requests

import openai_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def valid_response(content='{"translated":true}'):
    return {
        "id": "chatcmpl-test",
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 120,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens": 80,
            "total_tokens": 200,
            "completion_tokens_details": {"reasoning_tokens": 12},
        },
        "service_tier": "flex",
    }


class OpenAIClientTests(unittest.TestCase):
    def test_missing_key_blocks_before_transport(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(openai_client.requests, "post") as post,
        ):
            with self.assertRaisesRegex(openai_client.OpenAIClientError, "OPENAI_API_KEY"):
                openai_client.call_openai_json(prompt="translate")
        post.assert_not_called()

    def test_exact_request_shape_and_usage_envelope(self):
        response = FakeResponse(payload=valid_response())
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
            mock.patch.object(openai_client.requests, "post", return_value=response) as post,
        ):
            result = openai_client.call_openai_json(
                prompt="translate",
                model=openai_client.OPENAI_MODEL,
                max_output_tokens=4096,
                retries=0,
                temperature=0.2,
            )
        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"], {
            "model": "gpt-5.4-2026-03-05",
            "messages": [
                {"role": "system", "content": "Return strict JSON only. Do not use Markdown."},
                {"role": "user", "content": "translate"},
            ],
            "reasoning_effort": "none",
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 4096,
            "service_tier": "flex",
            "prompt_cache_key": "acc1-translation-json-v1",
        })
        self.assertEqual(kwargs["timeout"], 900)
        self.assertEqual(result.payload, {"translated": True})
        self.assertEqual(result.response_id, "chatcmpl-test")
        self.assertEqual(result.usage.input_tokens, 120)
        self.assertEqual(result.usage.cached_input_tokens, 0)
        self.assertEqual(result.usage.output_tokens, 80)
        self.assertEqual(result.usage.total_tokens, 200)
        self.assertEqual(result.usage.reasoning_tokens, 12)
        self.assertEqual(result.service_tier, "flex")

    def test_result_requires_explicit_service_tier_evidence(self):
        usage = openai_client.OpenAIUsage(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=1,
            total_tokens=2,
            reasoning_tokens=0,
        )
        with self.assertRaises(TypeError):
            openai_client.OpenAIJSONResult(payload={"ok": True}, usage=usage)

    def test_flex_tier_and_cached_input_are_proven_by_response(self):
        payload = valid_response()
        payload["usage"]["prompt_tokens_details"] = {"cached_tokens": 96}
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
            mock.patch.object(openai_client.requests, "post", return_value=FakeResponse(payload=payload)),
        ):
            result = openai_client.call_openai_json(prompt="translate")
        self.assertEqual(result.usage.cached_input_tokens, 96)

        for tier in (None, "default"):
            with self.subTest(tier=tier):
                invalid = valid_response()
                if tier is None:
                    invalid.pop("service_tier")
                else:
                    invalid["service_tier"] = tier
                with (
                    mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
                    mock.patch.object(openai_client.requests, "post", return_value=FakeResponse(payload=invalid)),
                ):
                    with self.assertRaisesRegex(openai_client.OpenAIClientError, "Flex service tier"):
                        openai_client.call_openai_json(prompt="translate")

    def test_invalid_cached_input_usage_is_rejected(self):
        payload = valid_response()
        payload["usage"]["prompt_tokens_details"] = {"cached_tokens": 121}
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
            mock.patch.object(openai_client.requests, "post", return_value=FakeResponse(payload=payload)),
        ):
            with self.assertRaisesRegex(openai_client.OpenAIClientError, "cached input tokens exceed"):
                openai_client.call_openai_json(prompt="translate")

    def test_malformed_completion_json_is_rejected(self):
        response = FakeResponse(payload=valid_response("```json\n{}\n```"))
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
            mock.patch.object(openai_client.requests, "post", return_value=response),
        ):
            with self.assertRaisesRegex(openai_client.OpenAIClientError, "not strict JSON"):
                openai_client.call_openai_json(prompt="translate")

    def test_missing_and_inconsistent_usage_are_rejected(self):
        cases = [
            ({**valid_response(), "usage": None}, "missing required token usage"),
            ({
                **valid_response(),
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 201,
                },
            }, "does not equal"),
            ({
                **valid_response(),
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                    "completion_tokens_details": {"reasoning_tokens": 81},
                },
            }, "exceeds output_tokens"),
        ]
        for payload, message in cases:
            with self.subTest(message=message):
                with (
                    mock.patch.dict(
                        os.environ,
                        {"OPENAI_API_KEY": "sk-private-test-key"},
                        clear=True,
                    ),
                    mock.patch.object(
                        openai_client.requests, "post",
                        return_value=FakeResponse(payload=payload),
                    ),
                ):
                    with self.assertRaisesRegex(
                        openai_client.OpenAIClientError, message,
                    ):
                        openai_client.call_openai_json(prompt="translate")

    def test_http_and_transport_errors_are_sanitized_without_retry(self):
        secret = "sk-private-test-key"
        http_response = FakeResponse(
            status_code=401,
            payload={"error": {"message": f"bad Authorization: Bearer {secret}"}},
        )
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=True),
            mock.patch.object(
                openai_client.requests, "post", return_value=http_response,
            ) as post,
        ):
            with self.assertRaises(openai_client.OpenAIClientError) as caught:
                openai_client.call_openai_json(prompt="translate")
        self.assertEqual(post.call_count, 1)
        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": secret}, clear=True),
            mock.patch.object(
                openai_client.requests, "post",
                side_effect=requests.Timeout(f"Bearer {secret}"),
            ) as post,
        ):
            with self.assertRaises(openai_client.OpenAIClientError) as caught:
                openai_client.call_openai_json(prompt="translate")
        self.assertEqual(post.call_count, 1)
        self.assertNotIn(secret, str(caught.exception))

    def test_only_exact_flex_resource_429_has_structured_rejection_type(self):
        exact = FakeResponse(
            status_code=429,
            payload={"error": {"message": (
                "Flex does not have sufficient resources available to fulfill "
                "your request. You can try again later."
            )}},
        )
        with (
            mock.patch.dict(
                os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True,
            ),
            mock.patch.object(
                openai_client.requests, "post", return_value=exact,
            ) as post,
        ):
            with self.assertRaises(
                openai_client.OpenAIFlexResourceUnavailableError,
            ) as caught:
                openai_client.call_openai_json(prompt="translate")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.service_tier, "flex")

        generic = FakeResponse(
            status_code=429,
            payload={"error": {"message": "Rate limit exceeded"}},
        )
        with (
            mock.patch.dict(
                os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True,
            ),
            mock.patch.object(
                openai_client.requests, "post", return_value=generic,
            ),
        ):
            with self.assertRaises(openai_client.OpenAIClientError) as generic_error:
                openai_client.call_openai_json(prompt="translate")
        self.assertNotIsInstance(
            generic_error.exception,
            openai_client.OpenAIFlexResourceUnavailableError,
        )

    def test_nonzero_retry_setting_is_rejected_before_transport(self):
        with (
            mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-private-test-key"}, clear=True),
            mock.patch.object(openai_client.requests, "post") as post,
        ):
            with self.assertRaisesRegex(openai_client.OpenAIClientError, "exactly zero"):
                openai_client.call_openai_json(prompt="translate", retries=1)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
