import hashlib
import unittest

from openai_flex_recovery import (
    FLEX_RESOURCE_UNAVAILABLE_MARKER,
    FlexRecoveryError,
    validate_openai_attempt_sequence,
)


def complete(index, request_hash):
    return {
        "index": index,
        "status": "COMPLETE",
        "request_sha256": request_hash,
    }


def rejected(index, request_hash):
    return {
        "index": index,
        "status": "REJECTED_FLEX_429",
        "request_sha256": request_hash,
        "model": "gpt-5.4-2026-03-05",
        "error_type": "OpenAIFlexResourceUnavailableError",
        "http_status": 429,
        "service_tier": "flex",
        "rejection_reason": "flex_resource_unavailable",
        "provider_documented_not_charged": True,
        "error_message_sha256": hashlib.sha256(
            FLEX_RESOURCE_UNAVAILABLE_MARKER.encode("utf-8")
        ).hexdigest(),
    }


class OpenAIFlexRecoveryTests(unittest.TestCase):
    def test_multiple_reconciled_rejections_allow_one_final_pending_retry(self):
        attempts = [
            complete(1, "1" * 64),
            rejected(2, "2" * 64),
            complete(3, "2" * 64),
            complete(4, "3" * 64),
            rejected(5, "4" * 64),
        ]
        self.assertEqual(
            validate_openai_attempt_sequence(attempts),
            (5, "4" * 64),
        )

    def test_every_nonfinal_rejection_requires_immediate_exact_completion(self):
        attempts = [
            rejected(1, "1" * 64),
            complete(2, "2" * 64),
        ]
        with self.assertRaisesRegex(
            FlexRecoveryError,
            "exact completed request",
        ):
            validate_openai_attempt_sequence(attempts)


if __name__ == "__main__":
    unittest.main()
