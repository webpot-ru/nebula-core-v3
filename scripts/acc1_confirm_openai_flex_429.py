#!/usr/bin/env python3
"""Confirm one parent Flex 429 from GitHub logs and seal resumable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai_flex_recovery import (  # noqa: E402
    FLEX_RESOURCE_UNAVAILABLE_MARKER,
    FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
    FlexRecoveryError,
    REJECTED_FLEX_429_ERROR_TYPE,
    REJECTED_FLEX_429_REASON,
    REJECTED_FLEX_429_STATUS,
    REJECTION_PROOF_SCHEMA,
    REQUIRED_SERVICE_TIER,
    SHA256_RE,
    canonical_hash,
    proof_self_hash,
    validate_rejected_attempt,
    validate_openai_attempt_sequence,
    validate_rejection_proof,
)


WORKFLOW_PATH = ".github/workflows/acc1_daily_episode.yml"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ConfirmationError(RuntimeError):
    pass


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfirmationError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ConfirmationError(f"{label} must be an object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ConfirmationError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfirmationError(f"{label} must be a positive integer") from exc
    if result < 1:
        raise ConfirmationError(f"{label} must be a positive integer")
    return result


def _github_headers(token: str) -> dict[str, str]:
    if not token:
        raise ConfirmationError("GH_TOKEN is required for Flex rejection confirmation")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_json(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise ConfirmationError("GitHub confirmation request failed") from exc
    if not 200 <= response.status_code < 300:
        raise ConfirmationError(
            f"GitHub confirmation HTTP status is {response.status_code}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConfirmationError("GitHub confirmation returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ConfirmationError("GitHub confirmation response must be an object")
    return payload


def _github_job_log(url: str, *, headers: dict[str, str]) -> bytes:
    try:
        response = requests.get(url, headers=headers, timeout=120)
    except requests.RequestException as exc:
        raise ConfirmationError("GitHub job-log request failed") from exc
    if not 200 <= response.status_code < 300:
        raise ConfirmationError(
            f"GitHub job-log HTTP status is {response.status_code}"
        )
    content = bytes(response.content)
    if not content or content.startswith(b"PK\x03\x04"):
        raise ConfirmationError("GitHub job log is empty or unexpectedly archived")
    return content


def _validate_parent_run(
    run: dict[str, Any], *, repository: str, run_id: int,
) -> int:
    if run.get("id") != run_id:
        raise ConfirmationError("GitHub parent run id mismatch")
    run_repository = run.get("repository")
    if (
        not isinstance(run_repository, dict)
        or run_repository.get("full_name") != repository
    ):
        raise ConfirmationError("GitHub parent run repository mismatch")
    path = str(run.get("path") or "").split("@", 1)[0]
    if path != WORKFLOW_PATH:
        raise ConfirmationError("GitHub parent run workflow mismatch")
    if run.get("event") != "workflow_dispatch" or run.get("conclusion") != "failure":
        raise ConfirmationError("GitHub parent run is not one failed manual dispatch")
    return _positive(run.get("run_attempt"), "GitHub parent run attempt")


def _select_failed_build_job(jobs: dict[str, Any]) -> int:
    candidates = [
        item for item in jobs.get("jobs") or []
        if isinstance(item, dict)
        and item.get("name") == "build"
        and item.get("conclusion") == "failure"
    ]
    if len(candidates) != 1:
        raise ConfirmationError("GitHub parent run must have exactly one failed build job")
    return _positive(candidates[0].get("id"), "GitHub build job id")


def _confirm_log(log_bytes: bytes) -> None:
    try:
        log_text = log_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfirmationError("GitHub job log is not UTF-8") from exc
    if log_text.count(FLEX_RESOURCE_UNAVAILABLE_MARKER) != 1:
        raise ConfirmationError(
            "GitHub job log does not contain exactly one confirmed Flex 429 rejection"
        )


def _normalize_attempt(
    journal: dict[str, Any], *, repository: str, run_id: int,
    run_attempt: int, job_id: int, job_log_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempts = journal.get("attempts")
    if (
        journal.get("provider") != "openai"
        or not isinstance(attempts, list)
        or not attempts
    ):
        raise ConfirmationError("OpenAI journal is not resumable")
    original_journal_sha256 = canonical_hash(journal)
    normalized = json.loads(json.dumps(journal))
    normalized_attempts = normalized["attempts"]
    last = normalized_attempts[-1]
    prior_attempts_are_reconciled = True
    if normalized_attempts[:-1]:
        try:
            _, prior_pending_hash = validate_openai_attempt_sequence(
                normalized_attempts[:-1]
            )
        except FlexRecoveryError:
            prior_attempts_are_reconciled = False
        else:
            prior_attempts_are_reconciled = prior_pending_hash is None
    is_legacy_ambiguous = (
        isinstance(last, dict)
        and last.get("index") == len(normalized_attempts)
        and last.get("status") == "AMBIGUOUS_ERROR"
        and last.get("error_type") == "OpenAIClientError"
        and SHA256_RE.fullmatch(str(last.get("request_sha256") or ""))
        and not any(
            field in last
            for field in ("usage", "response_sha256", "output_sha256", "task_id")
        )
    )
    if isinstance(last, dict) and last.get("status") == REJECTED_FLEX_429_STATUS:
        if not prior_attempts_are_reconciled:
            raise ConfirmationError(
                "Earlier Flex rejections are not exactly reconciled"
            )
        validate_rejected_attempt(last, expected_index=len(normalized_attempts))
    elif is_legacy_ambiguous is not True or not prior_attempts_are_reconciled:
        raise ConfirmationError(
            "Only one final legacy or confirmed Flex rejection can remain pending"
        )
    else:
        last.update({
            "status": REJECTED_FLEX_429_STATUS,
            "error_type": REJECTED_FLEX_429_ERROR_TYPE,
            "http_status": 429,
            "service_tier": REQUIRED_SERVICE_TIER,
            "rejection_reason": REJECTED_FLEX_429_REASON,
            "provider_documented_not_charged": True,
            "error_message_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
        })
    last["error_message_sha256"] = FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256
    if any(
        field in last
        for field in ("usage", "response_sha256", "output_sha256", "task_id")
    ):
        raise ConfirmationError("Confirmed Flex rejection contains completion evidence")
    last.update({
        "confirmation_source": "github_actions_job_log_v1",
        "confirmation_run_id": run_id,
        "confirmation_job_id": job_id,
        "confirmation_log_sha256": job_log_sha256,
    })
    rejection_index, pending_hash = validate_openai_attempt_sequence(
        normalized_attempts
    )
    if rejection_index != len(normalized_attempts) or pending_hash != last["request_sha256"]:
        raise ConfirmationError("Normalized Flex rejection is not an exact pending retry")
    proof = {
        "schema_version": REJECTION_PROOF_SCHEMA,
        "repository": repository,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "job_id": job_id,
        "attempt_index": last["index"],
        "request_sha256": last["request_sha256"],
        "original_journal_sha256": original_journal_sha256,
        "job_log_sha256": job_log_sha256,
        "matched_error_sha256": FLEX_RESOURCE_UNAVAILABLE_MARKER_SHA256,
        "rejected_attempt_sha256": canonical_hash(last),
        "publication_authorized": False,
    }
    proof["proof_sha256"] = proof_self_hash(proof)
    validate_rejection_proof(proof, rejected_attempt=last)
    return normalized, proof


def _existing_proof_attempt_index(
    journal: dict[str, Any], proof: dict[str, Any],
) -> int:
    attempts = journal.get("attempts")
    if not isinstance(attempts, list):
        raise ConfirmationError("OpenAI journal attempts are invalid")
    attempt_index = proof.get("attempt_index")
    if (
        isinstance(attempt_index, bool)
        or not isinstance(attempt_index, int)
        or attempt_index < 1
        or attempt_index > len(attempts)
    ):
        raise ConfirmationError("Flex rejection proof attempt index is invalid")
    validate_rejection_proof(
        proof, rejected_attempt=attempts[attempt_index - 1],
    )
    return attempt_index


def _reuse_existing_proof(
    journal: dict[str, Any], proof: dict[str, Any],
) -> None:
    """Backward-compatible strict proof validator used by focused tests."""
    _existing_proof_attempt_index(journal, proof)


def confirm_parent_flex_rejection(
    *, repository: str, run_id: int, journal_path: Path,
    proof_path: Path, token: str,
) -> str:
    repository = str(repository or "").strip()
    if not REPOSITORY_RE.fullmatch(repository):
        raise ConfirmationError("repository is invalid")
    run_id = _positive(run_id, "run_id")
    journal = _read_object(journal_path, "OpenAI journal")

    attempts = journal.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ConfirmationError("OpenAI journal attempts are invalid")
    try:
        pending_index, pending_hash = validate_openai_attempt_sequence(attempts)
    except FlexRecoveryError as exc:
        raise ConfirmationError("OpenAI journal has unsupported attempts") from exc
    if pending_index is None:
        return "NOT_REQUIRED"
    if pending_index != len(attempts) or pending_hash != attempts[-1].get(
        "request_sha256"
    ):
        raise ConfirmationError("OpenAI journal pending Flex retry is not final")
    if proof_path.exists():
        existing_proof = _read_object(proof_path, "Flex rejection proof")
        existing_index = _existing_proof_attempt_index(journal, existing_proof)
        if (
            existing_index == pending_index
            and existing_proof.get("run_id") == run_id
        ):
            return "EXISTING_PROOF_REUSED"

    headers = _github_headers(token)
    api_root = f"https://api.github.com/repos/{repository}/actions"
    run = _github_json(f"{api_root}/runs/{run_id}", headers=headers)
    run_attempt = _validate_parent_run(
        run, repository=repository, run_id=run_id,
    )
    jobs = _github_json(
        f"{api_root}/runs/{run_id}/jobs?per_page=100", headers=headers,
    )
    job_id = _select_failed_build_job(jobs)
    log_bytes = _github_job_log(
        f"{api_root}/jobs/{job_id}/logs", headers=headers,
    )
    _confirm_log(log_bytes)
    normalized, proof = _normalize_attempt(
        journal,
        repository=repository,
        run_id=run_id,
        run_attempt=run_attempt,
        job_id=job_id,
        job_log_sha256=hashlib.sha256(log_bytes).hexdigest(),
    )
    _atomic_json(journal_path, normalized)
    _atomic_json(proof_path, proof)
    return "CONFIRMED_AND_NORMALIZED"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repository", required=True)
    result.add_argument("--run-id", required=True, type=int)
    result.add_argument("--journal", required=True)
    result.add_argument("--proof", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    status = confirm_parent_flex_rejection(
        repository=args.repository,
        run_id=args.run_id,
        journal_path=Path(args.journal),
        proof_path=Path(args.proof),
        token=str(os.environ.get("GH_TOKEN") or ""),
    )
    print(json.dumps({
        "status": status,
        "run_id": args.run_id,
        "publication_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConfirmationError, FlexRecoveryError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
