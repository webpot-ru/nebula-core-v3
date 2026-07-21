#!/usr/bin/env python3
"""Create and validate the immutable acc1 cross-dispatch spend lease.

The lease is deliberately narrower than provider recovery.  It prevents a
second GitHub dispatch from spending again for the same ``episode_key``.  It
does not authorize publication and it never treats a previous provider call as
resumable.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit


LEASE_SCHEMA_VERSION = "acc1_paid_spend_lease_v3"
WORKFLOW_PATH = ".github/workflows/acc1_daily_episode.yml"
LEASE_FILENAME = "spend-lease.json"
LEASE_RETENTION_DAYS = 90
LOCK_SCOPE = "cross_dispatch_paid_generation_and_source_reservation_no_automatic_resume"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ARTIFACT_DIRECTORY_RE = re.compile(r"^(?P<run_id>[1-9][0-9]*)-(?P<artifact_id>[1-9][0-9]*)$")

PROVIDER_CONTRACT: dict[str, Any] = {
    "openai_translation": {
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "daily_token_cap": 3_000_000,
        "reasoning_effort": "none",
        "max_output_tokens": 16_384,
        "automatic_retries": 0,
    },
    "openai_review": {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "daily_token_cap": 500_000,
        "reasoning_effort": "none",
        "max_output_tokens": 16_384,
        "automatic_retries": 0,
    },
    "gemini": {
        "provider": "vectorengine",
        "model": "gemini-3.5-flash",
        "max_output_tokens": 16_384,
        "automatic_retries": 0,
    },
    "image": {
        "provider": "vectorengine",
        "model": "gpt-image-2",
        "size": "1536x864",
        "automatic_retries": 0,
    },
    "ai33": {
        "provider": "ai33",
        "model_id": "eleven_v3",
        "narrator_voice_id": "elevenlabs_JBFqnCBsd6RMkjVDRZzb",
        "comment_voice_id": "elevenlabs_MOgsVr0EwwxqQs5cNDhu",
        "speed": 1.0,
        "emotion_tags": False,
    },
}

CAP_KEYS = {
    "reddit_request_cap",
    "openai_call_cap",
    "openai_token_cap",
    "gemini_call_cap",
    "image_call_cap",
    "ai33_call_cap",
}
CONFIRMATION_KEYS = {
    "reddit_read",
    "openai_spend",
    "gemini_spend",
    "image_spend",
    "ai33_spend",
}
BINDING_KEYS = {
    "daily_plan_sha256",
    "config_sha256",
    "source_stage_sha256",
    "candidate_pool_sha256",
    "source_queue_sha256",
    "source_review_sha256",
}
RESERVED_SOURCE_KEYS = {
    "source_id",
    "source_url",
    "body_sha256",
    "story_signature",
    "source_reservation_sha256",
}
SOURCE_OVERLAP_KEYS = (
    "source_id",
    "source_url",
    "body_sha256",
    "story_signature",
)
LEASE_KEYS = {
    "schema_version",
    "repository",
    "workflow_path",
    "run_id",
    "run_attempt",
    "head_sha",
    "created_at",
    "episode_key",
    "production_date",
    "pilot_id",
    "source_bindings",
    "reserved_sources",
    "requested_caps",
    "confirmations",
    "provider_contract",
    "retention_days",
    "lock_scope",
    "publication_authorized",
    "lease_sha256",
}


class SpendLockError(RuntimeError):
    """Raised when the paid-generation lock cannot be proven safe."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def self_hash(value: dict[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return canonical_hash(payload)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpendLockError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise SpendLockError(f"{label} must contain a JSON object: {path}")
    return payload


def _require_sha256(value: Any, label: str) -> str:
    digest = str(value or "").strip().lower()
    if not SHA256_RE.fullmatch(digest):
        raise SpendLockError(f"{label} must be a SHA-256 digest")
    return digest


def _canonical_source_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").casefold()
    try:
        port = parsed.port
    except ValueError as exc:
        raise SpendLockError("reserved source URL has an invalid port") from exc
    if (
        parsed.scheme.casefold() != "https"
        or host not in {"reddit.com", "www.reddit.com", "old.reddit.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
    ):
        raise SpendLockError("reserved source URL must be canonical Reddit HTTPS")
    path = parsed.path.rstrip("/") or "/"
    return f"https://www.reddit.com{path}"


def _source_reservation_payload(source: dict[str, Any]) -> dict[str, str]:
    source_id = str(
        source.get("source_id") or source.get("post_id") or source.get("id") or ""
    ).strip().casefold()
    if not source_id:
        raise SpendLockError("candidate source_id is required for source reservation")
    source_url = _canonical_source_url(source.get("source_url") or source.get("url"))
    body = str(source.get("body") or source.get("source_body") or "")
    body_sha256 = _require_sha256(
        source.get("body_sha256") or source.get("source_body_sha256"),
        f"candidate source {source_id} body_sha256",
    )
    if not body or hashlib.sha256(body.encode("utf-8")).hexdigest() != body_sha256:
        raise SpendLockError(
            f"candidate source {source_id} body/hash is incomplete for source reservation"
        )
    story_signature = str(
        source.get("story_signature") or source.get("source_signature") or ""
    ).strip().casefold()
    if not story_signature:
        raise SpendLockError(
            f"candidate source {source_id} story_signature is required for source reservation"
        )
    payload = {
        "source_id": source_id,
        "source_url": source_url,
        "body_sha256": body_sha256,
        "story_signature": story_signature,
    }
    payload["source_reservation_sha256"] = canonical_hash(payload)
    return payload


def _derive_reserved_sources(candidate_pool: dict[str, Any]) -> list[dict[str, str]]:
    candidates = candidate_pool.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise SpendLockError("candidate pool has no sources to reserve")
    reservations: dict[str, dict[str, str]] = {}
    source_id_bindings: dict[str, str] = {}
    source_url_bindings: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise SpendLockError("candidate pool contains a non-object candidate")
        sources = candidate.get("sources")
        if not isinstance(sources, list) or not sources:
            raise SpendLockError("candidate pool candidate has no source objects to reserve")
        for source in sources:
            if not isinstance(source, dict):
                raise SpendLockError("candidate pool contains a non-object source")
            reservation = _source_reservation_payload(source)
            reservation_hash = reservation["source_reservation_sha256"]
            for field, bindings in (
                ("source_id", source_id_bindings),
                ("source_url", source_url_bindings),
            ):
                prior = bindings.get(reservation[field])
                if prior is not None and prior != reservation_hash:
                    raise SpendLockError(
                        f"candidate pool has conflicting {field} source reservation evidence"
                    )
                bindings[reservation[field]] = reservation_hash
            reservations[reservation_hash] = reservation
    return sorted(
        reservations.values(),
        key=lambda item: tuple(item[field] for field in SOURCE_OVERLAP_KEYS),
    )


def _validate_reserved_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise SpendLockError("spend lease reserved_sources must be a non-empty list")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != RESERVED_SOURCE_KEYS:
            raise SpendLockError(
                f"spend lease reserved source {index} fields are incomplete or unknown"
            )
        source_id = str(item.get("source_id") or "")
        if not source_id or source_id != source_id.strip().casefold():
            raise SpendLockError(f"spend lease reserved source {index} source_id is invalid")
        source_url = _canonical_source_url(item.get("source_url"))
        if source_url != item.get("source_url"):
            raise SpendLockError(f"spend lease reserved source {index} URL is not canonical")
        body_sha256 = _require_sha256(
            item.get("body_sha256"), f"spend lease reserved source {index} body_sha256",
        )
        story_signature = str(item.get("story_signature") or "")
        if not story_signature or story_signature != story_signature.strip().casefold():
            raise SpendLockError(
                f"spend lease reserved source {index} story_signature is invalid"
            )
        normalized_item = {
            "source_id": source_id,
            "source_url": source_url,
            "body_sha256": body_sha256,
            "story_signature": story_signature,
        }
        claimed = _require_sha256(
            item.get("source_reservation_sha256"),
            f"spend lease reserved source {index} self hash",
        )
        if canonical_hash(normalized_item) != claimed:
            raise SpendLockError(
                f"spend lease reserved source {index} self hash mismatch"
            )
        normalized_item["source_reservation_sha256"] = claimed
        normalized.append(normalized_item)
    expected = sorted(
        normalized,
        key=lambda item: tuple(item[field] for field in SOURCE_OVERLAP_KEYS),
    )
    if normalized != expected:
        raise SpendLockError("spend lease reserved_sources ordering is not canonical")
    hashes = [item["source_reservation_sha256"] for item in normalized]
    if len(hashes) != len(set(hashes)):
        raise SpendLockError("spend lease reserved_sources contains duplicate records")
    return normalized


def _positive_int(value: Any, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpendLockError(f"{label} must be a positive integer")
    if not 1 <= value <= maximum:
        raise SpendLockError(f"{label} must be between 1 and {maximum}")
    return value


def _exact_confirmation(value: Any, label: str) -> bool:
    if value is True or (isinstance(value, str) and value == "true"):
        return True
    raise SpendLockError(f"{label} requires exact true confirmation")


def _validate_episode_identity(episode_key: Any, production_date: Any, pilot_id: Any) -> None:
    date_value = str(production_date or "")
    pilot_value = str(pilot_id or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        raise SpendLockError("episode production_date must use exact YYYY-MM-DD")
    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError as exc:
        raise SpendLockError("episode production_date must use exact YYYY-MM-DD") from exc
    if not re.fullmatch(r"pilot_0[1-6]", pilot_value):
        raise SpendLockError("episode pilot_id is invalid")
    if episode_key != f"acc1/{date_value}/{pilot_value}":
        raise SpendLockError("episode key/date/pilot binding mismatch")


def _validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != "acc1_daily_episode_plan_v1":
        raise SpendLockError("daily plan schema is incompatible")
    if plan.get("status") != "PLANNED_ARTIFACT_ONLY" or plan.get("channel_id") != "acc1":
        raise SpendLockError("daily plan is not the acc1 artifact-only plan")
    _validate_episode_identity(
        plan.get("episode_key"), plan.get("production_date"), plan.get("pilot_id"),
    )
    _require_sha256(plan.get("config_sha256"), "daily plan config_sha256")
    if plan.get("provider_spend_authorized") is not False:
        raise SpendLockError("daily plan must not authorize provider spend")
    if plan.get("publication_authorized") is not False:
        raise SpendLockError("daily plan must not authorize publication")


def _validate_source_contract(
    plan: dict[str, Any],
    source_stage: dict[str, Any],
    candidate_pool: dict[str, Any],
    source_queue: dict[str, Any],
    source_review: dict[str, Any],
) -> dict[str, str]:
    _validate_plan(plan)
    daily_plan_sha256 = canonical_hash(plan)
    if source_stage.get("status") != "SOURCE_READY":
        raise SpendLockError("source stage is not SOURCE_READY")
    if source_stage.get("publication_authorized") is not False:
        raise SpendLockError("source stage must not authorize publication")
    source_stage_sha256 = _require_sha256(
        source_stage.get("source_stage_sha256"), "source stage self hash",
    )
    if self_hash(source_stage, "source_stage_sha256") != source_stage_sha256:
        raise SpendLockError("source stage self hash mismatch")

    if candidate_pool.get("status") != "SOURCE_FINALISTS_READY":
        raise SpendLockError("candidate pool is not SOURCE_FINALISTS_READY")
    if candidate_pool.get("publication_authorized") is not False:
        raise SpendLockError("candidate pool must not authorize publication")
    candidate_pool_sha256 = _require_sha256(
        candidate_pool.get("candidate_pool_sha256"), "candidate pool self hash",
    )
    if self_hash(candidate_pool, "candidate_pool_sha256") != candidate_pool_sha256:
        raise SpendLockError("candidate pool self hash mismatch")

    source_queue_sha256 = canonical_hash(source_queue)
    source_review_sha256 = canonical_hash(source_review)
    expected_stage_bindings = {
        "daily_plan_sha256": daily_plan_sha256,
        "source_queue_sha256": source_queue_sha256,
        "source_review_sha256": source_review_sha256,
        "candidate_pool_sha256": candidate_pool_sha256,
    }
    for field, expected in expected_stage_bindings.items():
        if source_stage.get(field) != expected:
            raise SpendLockError(f"source stage binding mismatch: {field}")
    if candidate_pool.get("daily_plan_sha256") != daily_plan_sha256:
        raise SpendLockError("candidate pool daily plan binding mismatch")
    if candidate_pool.get("episode_key") != plan.get("episode_key"):
        raise SpendLockError("candidate pool episode key binding mismatch")
    candidates = candidate_pool.get("candidates")
    candidate_count = candidate_pool.get("candidate_count")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or not isinstance(candidates, list)
        or candidate_count != len(candidates)
        or not 3 <= candidate_count <= 5
    ):
        raise SpendLockError(
            "candidate pool must bind an exact matching count of 3-5 source-review candidates"
        )

    return {
        "daily_plan_sha256": daily_plan_sha256,
        "config_sha256": _require_sha256(plan.get("config_sha256"), "config_sha256"),
        "source_stage_sha256": source_stage_sha256,
        "candidate_pool_sha256": candidate_pool_sha256,
        "source_queue_sha256": source_queue_sha256,
        "source_review_sha256": source_review_sha256,
    }


def build_lease(
    *,
    plan: dict[str, Any],
    source_stage: dict[str, Any],
    candidate_pool: dict[str, Any],
    source_queue: dict[str, Any],
    source_review: dict[str, Any],
    repository: str,
    workflow_path: str,
    run_id: int,
    run_attempt: int,
    head_sha: str,
    requested_caps: dict[str, Any],
    confirmations: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a self-verifying lease from the exact source-stage artifacts."""
    if not REPOSITORY_RE.fullmatch(repository):
        raise SpendLockError("repository must use exact owner/name form")
    if workflow_path != WORKFLOW_PATH:
        raise SpendLockError("workflow path does not match the acc1 daily factory")
    run_id = _positive_int(run_id, "run_id", 10**20)
    if run_attempt != 1:
        raise SpendLockError("paid lease creation is allowed only on run_attempt 1")
    normalized_head_sha = str(head_sha or "").strip().lower()
    if not HEAD_SHA_RE.fullmatch(normalized_head_sha):
        raise SpendLockError("head_sha must be an exact 40-character git commit SHA")
    if set(requested_caps) != CAP_KEYS:
        raise SpendLockError("requested caps are incomplete or contain unknown fields")
    caps = {
        "reddit_request_cap": _positive_int(
            requested_caps["reddit_request_cap"], "reddit_request_cap", 100,
        ),
        "openai_call_cap": _positive_int(
            requested_caps["openai_call_cap"], "openai_call_cap", 256,
        ),
        "openai_token_cap": _positive_int(
            requested_caps["openai_token_cap"], "openai_token_cap", 3_000_000,
        ),
        "gemini_call_cap": _positive_int(
            requested_caps["gemini_call_cap"], "gemini_call_cap", 256,
        ),
        "image_call_cap": _positive_int(
            requested_caps["image_call_cap"], "image_call_cap", 256,
        ),
        "ai33_call_cap": _positive_int(
            requested_caps["ai33_call_cap"], "ai33_call_cap", 256,
        ),
    }
    if set(confirmations) != CONFIRMATION_KEYS:
        raise SpendLockError("provider confirmations are incomplete or contain unknown fields")
    confirmed = {
        key: _exact_confirmation(confirmations[key], f"confirm_{key}")
        for key in sorted(CONFIRMATION_KEYS)
    }
    bindings = _validate_source_contract(
        plan, source_stage, candidate_pool, source_queue, source_review,
    )
    reserved_sources = _derive_reserved_sources(candidate_pool)
    timestamp = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise SpendLockError("created_at must be an ISO-8601 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
    except ValueError as exc:
        raise SpendLockError("created_at is not a valid ISO-8601 UTC timestamp") from exc

    lease: dict[str, Any] = {
        "schema_version": LEASE_SCHEMA_VERSION,
        "repository": repository,
        "workflow_path": workflow_path,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "head_sha": normalized_head_sha,
        "created_at": timestamp,
        "episode_key": plan["episode_key"],
        "production_date": plan["production_date"],
        "pilot_id": plan["pilot_id"],
        "source_bindings": bindings,
        "reserved_sources": reserved_sources,
        "requested_caps": caps,
        "confirmations": confirmed,
        "provider_contract": copy.deepcopy(PROVIDER_CONTRACT),
        "retention_days": LEASE_RETENTION_DAYS,
        "lock_scope": LOCK_SCOPE,
        "publication_authorized": False,
    }
    lease["lease_sha256"] = self_hash(lease, "lease_sha256")
    validate_lease(
        lease,
        expected_repository=repository,
        expected_workflow_path=workflow_path,
    )
    return lease


def validate_lease(
    lease: dict[str, Any],
    *,
    expected_repository: str,
    expected_workflow_path: str,
) -> None:
    if set(lease) != LEASE_KEYS:
        raise SpendLockError("spend lease fields are incomplete or unknown")
    if lease.get("schema_version") != LEASE_SCHEMA_VERSION:
        raise SpendLockError("spend lease schema is unknown")
    if lease.get("repository") != expected_repository:
        raise SpendLockError("spend lease repository binding mismatch")
    if lease.get("workflow_path") != expected_workflow_path:
        raise SpendLockError("spend lease workflow binding mismatch")
    _positive_int(lease.get("run_id"), "lease run_id", 10**20)
    if lease.get("run_attempt") != 1:
        raise SpendLockError("spend lease run_attempt is incompatible")
    if not HEAD_SHA_RE.fullmatch(str(lease.get("head_sha") or "")):
        raise SpendLockError("spend lease head_sha is invalid")
    _validate_episode_identity(
        lease.get("episode_key"), lease.get("production_date"), lease.get("pilot_id"),
    )
    created_at = str(lease.get("created_at") or "")
    if not created_at.endswith("Z"):
        raise SpendLockError("spend lease created_at must be UTC")
    try:
        datetime.fromisoformat(created_at[:-1] + "+00:00")
    except ValueError as exc:
        raise SpendLockError("spend lease created_at is invalid") from exc
    if lease.get("publication_authorized") is not False:
        raise SpendLockError("spend lease cannot authorize publication")
    if lease.get("retention_days") != LEASE_RETENTION_DAYS:
        raise SpendLockError("spend lease retention policy is incompatible")
    if lease.get("lock_scope") != LOCK_SCOPE:
        raise SpendLockError("spend lease scope is incompatible")
    if lease.get("provider_contract") != PROVIDER_CONTRACT:
        raise SpendLockError("spend lease provider/model contract is incompatible")
    bindings = lease.get("source_bindings")
    if not isinstance(bindings, dict) or set(bindings) != BINDING_KEYS:
        raise SpendLockError("spend lease source bindings are incomplete or unknown")
    for field in BINDING_KEYS:
        _require_sha256(bindings.get(field), f"spend lease {field}")
    _validate_reserved_sources(lease.get("reserved_sources"))
    caps = lease.get("requested_caps")
    if not isinstance(caps, dict) or set(caps) != CAP_KEYS:
        raise SpendLockError("spend lease caps are incomplete or unknown")
    _positive_int(caps["reddit_request_cap"], "lease reddit_request_cap", 100)
    _positive_int(caps["openai_call_cap"], "lease openai_call_cap", 256)
    _positive_int(caps["openai_token_cap"], "lease openai_token_cap", 3_000_000)
    for field in ("gemini_call_cap", "image_call_cap", "ai33_call_cap"):
        _positive_int(caps[field], f"lease {field}", 256)
    confirmations = lease.get("confirmations")
    if not isinstance(confirmations, dict) or set(confirmations) != CONFIRMATION_KEYS:
        raise SpendLockError("spend lease confirmations are incomplete or unknown")
    if any(value is not True for value in confirmations.values()):
        raise SpendLockError("spend lease confirmations must all be exact true")
    claimed = _require_sha256(lease.get("lease_sha256"), "spend lease self hash")
    if self_hash(lease, "lease_sha256") != claimed:
        raise SpendLockError("spend lease self hash mismatch")


def validate_lease_for_production(
    lease: dict[str, Any],
    *,
    plan: dict[str, Any],
    source_stage: dict[str, Any],
    candidate_pool: dict[str, Any],
    source_queue: dict[str, Any],
    source_review: dict[str, Any],
    repository: str,
    workflow_path: str,
    requested_caps: dict[str, Any],
    confirmations: dict[str, Any],
    provider_contract: dict[str, Any],
    run_id: int | None = None,
    run_attempt: int | None = None,
    head_sha: str | None = None,
) -> None:
    """Bind the persisted lease to the exact imminent paid factory call."""
    validate_lease(
        lease,
        expected_repository=repository,
        expected_workflow_path=workflow_path,
    )
    expected_bindings = _validate_source_contract(
        plan, source_stage, candidate_pool, source_queue, source_review,
    )
    if lease.get("source_bindings") != expected_bindings:
        raise SpendLockError("spend lease does not bind the exact source artifacts")
    if lease.get("reserved_sources") != _derive_reserved_sources(candidate_pool):
        raise SpendLockError("spend lease does not bind the exact reserved source identities")
    if set(requested_caps) != CAP_KEYS:
        raise SpendLockError("production caps are incomplete or contain unknown fields")
    expected_caps = {
        "reddit_request_cap": _positive_int(
            requested_caps["reddit_request_cap"], "reddit_request_cap", 100,
        ),
        "openai_call_cap": _positive_int(
            requested_caps["openai_call_cap"], "openai_call_cap", 256,
        ),
        "openai_token_cap": _positive_int(
            requested_caps["openai_token_cap"], "openai_token_cap", 3_000_000,
        ),
        "gemini_call_cap": _positive_int(
            requested_caps["gemini_call_cap"], "gemini_call_cap", 256,
        ),
        "image_call_cap": _positive_int(
            requested_caps["image_call_cap"], "image_call_cap", 256,
        ),
        "ai33_call_cap": _positive_int(
            requested_caps["ai33_call_cap"], "ai33_call_cap", 256,
        ),
    }
    if lease.get("requested_caps") != expected_caps:
        raise SpendLockError("spend lease does not bind the exact production caps")
    if set(confirmations) != CONFIRMATION_KEYS:
        raise SpendLockError("production confirmations are incomplete or contain unknown fields")
    expected_confirmations = {
        key: _exact_confirmation(confirmations[key], f"confirm_{key}")
        for key in sorted(CONFIRMATION_KEYS)
    }
    if lease.get("confirmations") != expected_confirmations:
        raise SpendLockError("spend lease does not bind the exact confirmations")
    if provider_contract != PROVIDER_CONTRACT:
        raise SpendLockError("factory provider/model contract drifted from the spend-lock contract")
    if lease.get("provider_contract") != provider_contract:
        raise SpendLockError("spend lease does not bind the exact provider/model contract")
    if run_id is not None and lease.get("run_id") != _positive_int(run_id, "run_id", 10**20):
        raise SpendLockError("spend lease run_id does not match the production run")
    if run_attempt is not None and lease.get("run_attempt") != run_attempt:
        raise SpendLockError("spend lease run_attempt does not match the production run")
    if head_sha is not None:
        normalized_head_sha = str(head_sha or "").strip().lower()
        if not HEAD_SHA_RE.fullmatch(normalized_head_sha):
            raise SpendLockError("production head_sha is invalid")
        if lease.get("head_sha") != normalized_head_sha:
            raise SpendLockError("spend lease head_sha does not match the production code")


def scan_leases(
    *,
    plan: dict[str, Any],
    leases_root: Path,
    repository: str,
    workflow_path: str,
    current_run_id: int,
    source_stage: dict[str, Any] | None = None,
    candidate_pool: dict[str, Any] | None = None,
    source_queue: dict[str, Any] | None = None,
    source_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Block on invalid leases, exact episodes, or reserved-source overlap."""
    _validate_plan(plan)
    source_inputs = (source_stage, candidate_pool, source_queue, source_review)
    if any(item is not None for item in source_inputs) and not all(
        item is not None for item in source_inputs
    ):
        raise SpendLockError(
            "source reservation scan requires source-stage, candidate-pool, "
            "source-queue, and source-review together"
        )
    current_reserved_sources: list[dict[str, str]] | None = None
    if all(item is not None for item in source_inputs):
        assert source_stage is not None
        assert candidate_pool is not None
        assert source_queue is not None
        assert source_review is not None
        _validate_source_contract(
            plan, source_stage, candidate_pool, source_queue, source_review,
        )
        current_reserved_sources = _derive_reserved_sources(candidate_pool)
    current_tokens = {
        (field, item[field])
        for item in (current_reserved_sources or [])
        for field in SOURCE_OVERLAP_KEYS
    }
    current_run_id = _positive_int(current_run_id, "current_run_id", 10**20)
    root = Path(leases_root)
    if not root.is_dir():
        raise SpendLockError(f"spend lease scan root is missing: {root}")
    unexpected_top_level = [path for path in root.iterdir() if not path.is_dir()]
    if unexpected_top_level:
        raise SpendLockError("spend lease scan root contains an unreadable/unknown artifact")

    inspected = 0
    for artifact_dir in sorted(root.iterdir(), key=lambda item: item.name):
        directory_match = ARTIFACT_DIRECTORY_RE.fullmatch(artifact_dir.name)
        if directory_match is None:
            raise SpendLockError(f"spend lease artifact directory is unknown: {artifact_dir.name}")
        owner_run_id = int(directory_match.group("run_id"))
        lease_files = list(artifact_dir.rglob(LEASE_FILENAME))
        if len(lease_files) != 1:
            raise SpendLockError(
                f"spend lease artifact {artifact_dir.name} must contain exactly one {LEASE_FILENAME}"
            )
        lease = _read_object(lease_files[0], "spend lease")
        validate_lease(
            lease,
            expected_repository=repository,
            expected_workflow_path=workflow_path,
        )
        if lease.get("run_id") != owner_run_id:
            raise SpendLockError("spend lease run id does not match GitHub artifact provenance")
        if owner_run_id == current_run_id:
            raise SpendLockError("current run already owns a paid spend lease; rerun is forbidden")
        inspected += 1
        if lease.get("episode_key") == plan.get("episode_key"):
            raise SpendLockError(
                "episode is already protected by paid spend lease from GitHub run "
                f"{owner_run_id}; automatic re-spend is forbidden"
            )
        if current_reserved_sources is not None:
            prior_tokens = {
                (field, item[field])
                for item in lease["reserved_sources"]
                for field in SOURCE_OVERLAP_KEYS
            }
            overlap = current_tokens.intersection(prior_tokens)
            if overlap:
                overlap_fields = ", ".join(sorted({field for field, _ in overlap}))
                raise SpendLockError(
                    "candidate source pool overlaps paid source reservation from GitHub run "
                    f"{owner_run_id} via {overlap_fields}; automatic re-spend is forbidden"
                )
    return {
        "status": "SPEND_LOCK_CLEAR",
        "episode_key": plan["episode_key"],
        "inspected_leases": inspected,
        "source_reservation_checked": current_reserved_sources is not None,
        "current_reserved_source_count": len(current_reserved_sources or []),
        "publication_authorized": False,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser(
        "scan",
        help="fail on a prior exact-episode lease or post-source reservation overlap",
    )
    scan.add_argument("--plan", required=True)
    scan.add_argument("--leases-root", required=True)
    scan.add_argument("--repository", required=True)
    scan.add_argument("--workflow-path", default=WORKFLOW_PATH)
    scan.add_argument("--current-run-id", required=True, type=int)
    scan.add_argument("--source-stage")
    scan.add_argument("--candidate-pool")
    scan.add_argument("--source-queue")
    scan.add_argument("--source-review")

    create = subparsers.add_parser("create", help="create a source-bound paid spend lease")
    create.add_argument("--plan", required=True)
    create.add_argument("--source-stage", required=True)
    create.add_argument("--candidate-pool", required=True)
    create.add_argument("--source-queue", required=True)
    create.add_argument("--source-review", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--repository", required=True)
    create.add_argument("--workflow-path", default=WORKFLOW_PATH)
    create.add_argument("--run-id", required=True, type=int)
    create.add_argument("--run-attempt", required=True, type=int)
    create.add_argument("--head-sha", required=True)
    create.add_argument("--reddit-request-cap", required=True, type=int)
    create.add_argument("--openai-call-cap", required=True, type=int)
    create.add_argument("--openai-token-cap", required=True, type=int)
    create.add_argument("--gemini-call-cap", required=True, type=int)
    create.add_argument("--image-call-cap", required=True, type=int)
    create.add_argument("--ai33-call-cap", required=True, type=int)
    create.add_argument("--confirm-reddit-read", required=True)
    create.add_argument("--confirm-openai-spend", required=True)
    create.add_argument("--confirm-gemini-spend", required=True)
    create.add_argument("--confirm-image-spend", required=True)
    create.add_argument("--confirm-ai33-spend", required=True)
    create.add_argument("--created-at")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    plan = _read_object(Path(args.plan), "daily plan")
    if args.command == "scan":
        source_paths = {
            "source_stage": args.source_stage,
            "candidate_pool": args.candidate_pool,
            "source_queue": args.source_queue,
            "source_review": args.source_review,
        }
        if any(source_paths.values()) and not all(source_paths.values()):
            raise SpendLockError(
                "source reservation scan requires all four source artifact paths"
            )
        source_payloads = {
            key: _read_object(Path(path), key.replace("_", " "))
            for key, path in source_paths.items()
            if path
        }
        result = scan_leases(
            plan=plan,
            leases_root=Path(args.leases_root),
            repository=args.repository,
            workflow_path=args.workflow_path,
            current_run_id=args.current_run_id,
            source_stage=source_payloads.get("source_stage"),
            candidate_pool=source_payloads.get("candidate_pool"),
            source_queue=source_payloads.get("source_queue"),
            source_review=source_payloads.get("source_review"),
        )
    else:
        result = build_lease(
            plan=plan,
            source_stage=_read_object(Path(args.source_stage), "source stage"),
            candidate_pool=_read_object(Path(args.candidate_pool), "candidate pool"),
            source_queue=_read_object(Path(args.source_queue), "source queue"),
            source_review=_read_object(Path(args.source_review), "source review"),
            repository=args.repository,
            workflow_path=args.workflow_path,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            head_sha=args.head_sha,
            requested_caps={
                "reddit_request_cap": args.reddit_request_cap,
                "openai_call_cap": args.openai_call_cap,
                "openai_token_cap": args.openai_token_cap,
                "gemini_call_cap": args.gemini_call_cap,
                "image_call_cap": args.image_call_cap,
                "ai33_call_cap": args.ai33_call_cap,
            },
            confirmations={
                "reddit_read": args.confirm_reddit_read,
                "openai_spend": args.confirm_openai_spend,
                "gemini_spend": args.confirm_gemini_spend,
                "image_spend": args.confirm_image_spend,
                "ai33_spend": args.confirm_ai33_spend,
            },
            created_at=args.created_at,
        )
        _atomic_json(Path(args.output), result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpendLockError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
