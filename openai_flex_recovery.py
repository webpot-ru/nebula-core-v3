"""Fail-closed journal contract for one confirmed OpenAI Flex 429 rejection."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


REJECTED_FLEX_429_STATUS = "REJECTED_FLEX_429"
REJECTED_FLEX_429_ERROR_TYPE = "OpenAIFlexResourceUnavailableError"
REJECTED_FLEX_429_REASON = "flex_resource_unavailable"
REQUIRED_SERVICE_TIER = "flex"
REJECTION_PROOF_SCHEMA = "acc1_openai_flex_429_rejection_v1"
FLEX_RESOURCE_UNAVAILABLE_MESSAGE = (
    "Flex does not have sufficient resources available "
    "to fulfill your request."
)
FLEX_RESOURCE_UNAVAILABLE_MARKER = (
    f"OpenAI HTTP 429: {FLEX_RESOURCE_UNAVAILABLE_MESSAGE}"
)
FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256 = hashlib.sha256(
    FLEX_RESOURCE_UNAVAILABLE_MARKER.encode("utf-8")
).hexdigest()
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class FlexRecoveryError(RuntimeError):
    """Raised when a Flex rejection or its proof is not exact."""


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def proof_self_hash(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("proof_sha256", None)
    return canonical_hash(payload)


def validate_rejected_attempt(
    attempt: dict[str, Any], *, expected_index: int,
) -> None:
    if attempt.get("index") != expected_index:
        raise FlexRecoveryError("Flex rejection attempt index is invalid")
    if attempt.get("status") != REJECTED_FLEX_429_STATUS:
        raise FlexRecoveryError("OpenAI attempt is not a confirmed Flex rejection")
    if attempt.get("error_type") != REJECTED_FLEX_429_ERROR_TYPE:
        raise FlexRecoveryError("Flex rejection error type is invalid")
    if attempt.get("http_status") != 429:
        raise FlexRecoveryError("Flex rejection HTTP status is invalid")
    if attempt.get("service_tier") != REQUIRED_SERVICE_TIER:
        raise FlexRecoveryError("Flex rejection service tier is invalid")
    if attempt.get("rejection_reason") != REJECTED_FLEX_429_REASON:
        raise FlexRecoveryError("Flex rejection reason is invalid")
    if attempt.get("provider_documented_not_charged") is not True:
        raise FlexRecoveryError("Flex rejection billing evidence is absent")
    if not SHA256_RE.fullmatch(str(attempt.get("request_sha256") or "")):
        raise FlexRecoveryError("Flex rejection request hash is invalid")
    if (
        attempt.get("error_message_sha256")
        != FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256
    ):
        raise FlexRecoveryError("Flex rejection message hash is invalid")
    if any(
        field in attempt
        for field in ("usage", "response_sha256", "output_sha256", "task_id")
    ):
        raise FlexRecoveryError("Flex rejection contains completion evidence")


def validate_openai_attempt_sequence(
    attempts: list[dict[str, Any]],
) -> tuple[int | None, str | None]:
    """Return the final pending rejection and exact retry hash, if any.

    Earlier confirmed Flex rejections are valid only when the immediately
    following attempt completed the exact same request hash.  This permits a
    long-running bounded job to survive more than one independent Flex
    capacity rejection without weakening the journal's ordering guarantees.
    """
    if not attempts:
        raise FlexRecoveryError("OpenAI attempt journal is empty")
    index = 1
    while index <= len(attempts):
        attempt = attempts[index - 1]
        if not isinstance(attempt, dict) or attempt.get("index") != index:
            raise FlexRecoveryError("OpenAI attempt sequence is invalid")
        status = attempt.get("status")
        if status == "COMPLETE":
            index += 1
            continue
        if status != REJECTED_FLEX_429_STATUS:
            raise FlexRecoveryError("OpenAI attempt journal has an unresolved attempt")
        validate_rejected_attempt(attempt, expected_index=index)
        if index == len(attempts):
            return index, str(attempt["request_sha256"])
        retry = attempts[index]
        if (
            not isinstance(retry, dict)
            or retry.get("index") != index + 1
            or retry.get("status") != "COMPLETE"
            or retry.get("request_sha256") != attempt.get("request_sha256")
        ):
            raise FlexRecoveryError(
                "Flex rejection is not followed by one exact completed request"
            )
        index += 2
    return None, None


def validate_rejection_proof(
    proof: dict[str, Any], *, rejected_attempt: dict[str, Any],
) -> None:
    if proof.get("schema_version") != REJECTION_PROOF_SCHEMA:
        raise FlexRecoveryError("Flex rejection proof schema mismatch")
    if proof.get("publication_authorized") is not False:
        raise FlexRecoveryError("Flex rejection proof must not authorize publication")
    if not REPOSITORY_RE.fullmatch(str(proof.get("repository") or "")):
        raise FlexRecoveryError("Flex rejection proof repository is invalid")
    for field in ("run_id", "run_attempt", "job_id", "attempt_index"):
        value = proof.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise FlexRecoveryError(f"Flex rejection proof {field} is invalid")
    for field in (
        "request_sha256", "original_journal_sha256", "job_log_sha256",
        "matched_error_sha256", "rejected_attempt_sha256", "proof_sha256",
    ):
        if not SHA256_RE.fullmatch(str(proof.get(field) or "")):
            raise FlexRecoveryError(f"Flex rejection proof {field} is invalid")
    if proof.get("attempt_index") != rejected_attempt.get("index"):
        raise FlexRecoveryError("Flex rejection proof attempt index mismatch")
    if proof.get("request_sha256") != rejected_attempt.get("request_sha256"):
        raise FlexRecoveryError("Flex rejection proof request hash mismatch")
    if proof.get("rejected_attempt_sha256") != canonical_hash(rejected_attempt):
        raise FlexRecoveryError("Flex rejection proof attempt binding mismatch")
    if proof_self_hash(proof) != proof.get("proof_sha256"):
        raise FlexRecoveryError("Flex rejection proof self hash mismatch")
