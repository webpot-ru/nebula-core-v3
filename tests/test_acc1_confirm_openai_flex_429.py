import json
import tempfile
import unittest
from pathlib import Path

from openai_flex_recovery import (
    FLEX_RESOURCE_UNAVAILABLE_MARKER,
    FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
    REJECTED_FLEX_429_ERROR_TYPE,
    REJECTED_FLEX_429_REASON,
    REJECTED_FLEX_429_STATUS,
    validate_rejection_proof,
)
from scripts.acc1_confirm_openai_flex_429 import (
    ConfirmationError,
    _confirm_log,
    _normalize_attempt,
    _reuse_existing_proof,
    confirm_parent_flex_rejection,
)


def legacy_journal():
    usage = {
        "input_tokens": 10,
        "cached_input_tokens": 0,
        "output_tokens": 2,
        "total_tokens": 12,
        "reasoning_tokens": 0,
    }
    return {
        "version": 1,
        "provider": "openai",
        "cap": 128,
        "token_cap": 750_000,
        "usage_totals": dict(usage),
        "attempts": [
            {
                "index": 1,
                "status": "COMPLETE",
                "request_sha256": "1" * 64,
                "usage": dict(usage),
            },
            {
                "index": 2,
                "status": "AMBIGUOUS_ERROR",
                "request_sha256": "2" * 64,
                "model": "gpt-5.4-2026-03-05",
                "error_type": "OpenAIClientError",
            },
        ],
        "publication_authorized": False,
    }


class Acc1ConfirmOpenAIFlex429Tests(unittest.TestCase):
    def test_exact_log_normalizes_only_final_legacy_attempt_and_seals_proof(self):
        log = f"trace\n{FLEX_RESOURCE_UNAVAILABLE_MARKER}\n".encode()
        _confirm_log(log)
        normalized, proof = _normalize_attempt(
            legacy_journal(),
            repository="webpot-ru/nebula-core-v3",
            run_id=30280795084,
            run_attempt=1,
            job_id=90026404308,
            job_log_sha256="3" * 64,
        )
        rejected = normalized["attempts"][-1]
        self.assertEqual(rejected["status"], "REJECTED_FLEX_429")
        self.assertEqual(rejected["request_sha256"], "2" * 64)
        self.assertEqual(rejected["http_status"], 429)
        self.assertNotIn("usage", rejected)
        self.assertEqual(normalized["usage_totals"]["total_tokens"], 12)
        validate_rejection_proof(proof, rejected_attempt=rejected)
        _reuse_existing_proof(normalized, proof)

    def test_generic_or_duplicate_429_log_is_not_confirmation(self):
        with self.assertRaisesRegex(ConfirmationError, "exactly one"):
            _confirm_log(b"OpenAI HTTP 429: Rate limit exceeded")
        duplicate = (
            FLEX_RESOURCE_UNAVAILABLE_MARKER
            + "\n"
            + FLEX_RESOURCE_UNAVAILABLE_MARKER
        ).encode()
        with self.assertRaisesRegex(ConfirmationError, "exactly one"):
            _confirm_log(duplicate)

    def test_already_structured_final_rejection_is_sealed_after_log_confirmation(self):
        journal = legacy_journal()
        rejected = journal["attempts"][-1]
        rejected.update({
            "status": REJECTED_FLEX_429_STATUS,
            "error_type": REJECTED_FLEX_429_ERROR_TYPE,
            "http_status": 429,
            "service_tier": "flex",
            "rejection_reason": REJECTED_FLEX_429_REASON,
            "provider_documented_not_charged": True,
            "error_message_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
        })
        normalized, proof = _normalize_attempt(
            journal,
            repository="webpot-ru/nebula-core-v3",
            run_id=30280795084,
            run_attempt=1,
            job_id=90026404308,
            job_log_sha256="3" * 64,
        )
        sealed = normalized["attempts"][-1]
        self.assertEqual(sealed["status"], REJECTED_FLEX_429_STATUS)
        self.assertEqual(sealed["confirmation_run_id"], 30280795084)
        validate_rejection_proof(proof, rejected_attempt=sealed)

    def test_prior_rejection_may_be_reconciled_before_new_final_rejection(self):
        journal = legacy_journal()
        first_rejected = journal["attempts"].pop()
        first_rejected.update({
            "status": REJECTED_FLEX_429_STATUS,
            "error_type": REJECTED_FLEX_429_ERROR_TYPE,
            "http_status": 429,
            "service_tier": "flex",
            "rejection_reason": REJECTED_FLEX_429_REASON,
            "provider_documented_not_charged": True,
            "error_message_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
        })
        journal["attempts"].extend([
            first_rejected,
            {
                "index": 3,
                "status": "COMPLETE",
                "request_sha256": first_rejected["request_sha256"],
                "usage": {
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "reasoning_tokens": 0,
                },
            },
            {
                "index": 4,
                "status": "REJECTED_FLEX_429",
                "request_sha256": "4" * 64,
                "model": "gpt-5.4-2026-03-05",
                "error_type": REJECTED_FLEX_429_ERROR_TYPE,
                "http_status": 429,
                "service_tier": "flex",
                "rejection_reason": REJECTED_FLEX_429_REASON,
                "provider_documented_not_charged": True,
                "error_message_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
            },
        ])
        journal["usage_totals"]["input_tokens"] += 1
        journal["usage_totals"]["output_tokens"] += 1
        journal["usage_totals"]["total_tokens"] += 2
        normalized, proof = _normalize_attempt(
            journal,
            repository="webpot-ru/nebula-core-v3",
            run_id=30348347285,
            run_attempt=1,
            job_id=90239791494,
            job_log_sha256="5" * 64,
        )
        self.assertEqual(proof["attempt_index"], 4)
        validate_rejection_proof(
            proof,
            rejected_attempt=normalized["attempts"][3],
        )

    def test_completed_parent_is_noop_without_github_request(self):
        journal = legacy_journal()
        journal["attempts"].pop()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal_path = root / "openai.json"
            proof_path = root / "proof.json"
            journal_path.write_text(json.dumps(journal), encoding="utf-8")
            status = confirm_parent_flex_rejection(
                repository="webpot-ru/nebula-core-v3",
                run_id=101,
                journal_path=journal_path,
                proof_path=proof_path,
                token="",
            )
        self.assertEqual(status, "NOT_REQUIRED")


if __name__ == "__main__":
    unittest.main()
