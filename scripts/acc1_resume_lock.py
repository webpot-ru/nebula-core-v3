#!/usr/bin/env python3
"""Create and validate one fail-closed continuation lock for a paid acc1 run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.acc1_spend_lock import WORKFLOW_PATH, validate_lease
except ModuleNotFoundError:  # Direct ``python scripts/acc1_resume_lock.py`` execution.
    from acc1_spend_lock import WORKFLOW_PATH, validate_lease


SCHEMA = "acc1_paid_resume_lease_v1"
FILENAME = "resume-spend-lease.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ARTIFACT_DIRECTORY_RE = re.compile(r"^(?P<run_id>[1-9][0-9]*)-(?P<artifact_id>[1-9][0-9]*)$")


class ResumeLockError(RuntimeError):
    pass


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def self_hash(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("resume_lease_sha256", None)
    return canonical_hash(payload)


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResumeLockError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ResumeLockError(f"{label} must be an object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ResumeLockError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ResumeLockError(f"{label} must be a positive integer") from exc
    if result < 1:
        raise ResumeLockError(f"{label} must be a positive integer")
    return result


def scan_existing(root: Path, *, parent_run_id: int, repository: str) -> int:
    if not root.is_dir():
        raise ResumeLockError("resume lock scan root is missing")
    inspected = 0
    for directory in sorted(root.iterdir(), key=lambda item: item.name):
        match = ARTIFACT_DIRECTORY_RE.fullmatch(directory.name)
        if match is None or not directory.is_dir():
            raise ResumeLockError("resume lock artifact directory is unknown")
        files = list(directory.rglob(FILENAME))
        if len(files) != 1:
            raise ResumeLockError("resume lock artifact must contain exactly one lease")
        lease = read_object(files[0], "resume lease")
        validate_resume_lease(lease, repository=repository)
        if lease["run_id"] != int(match.group("run_id")):
            raise ResumeLockError("resume lease run id does not match artifact provenance")
        inspected += 1
        if lease["parent_run_id"] == parent_run_id:
            raise ResumeLockError(
                f"parent run {parent_run_id} already has resume lease from run {lease['run_id']}"
            )
    return inspected


def build_resume_lease(
    *, parent_lease: dict[str, Any], topic_input: dict[str, Any],
    producer_review: dict[str, Any], critic_review: dict[str, Any],
    openai_journal: dict[str, Any], parent_run_id: int, run_id: int,
    run_attempt: int, head_sha: str, repository: str,
    openai_call_cap: int, openai_token_cap: int, image_call_cap: int,
    ai33_call_cap: int,
    parent_resume_lease: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_lease(
        parent_lease, expected_repository=repository,
        expected_workflow_path=WORKFLOW_PATH,
    )
    parent_run_id = _positive(parent_run_id, "parent_run_id")
    if parent_resume_lease is None:
        if parent_lease.get("run_id") != parent_run_id:
            raise ResumeLockError("parent lease run id mismatch")
    else:
        validate_resume_lease(
            parent_resume_lease,
            repository=repository,
            run_id=parent_run_id,
        )
        if canonical_hash(parent_lease) != parent_resume_lease.get(
            "parent_spend_lease_sha256"
        ):
            raise ResumeLockError("parent spend lease does not match resume ancestry")
    attempts = openai_journal.get("attempts")
    if (
        openai_journal.get("provider") != "openai"
        or not isinstance(attempts, list)
        or not attempts
        or any(item.get("status") != "COMPLETE" for item in attempts if isinstance(item, dict))
        or any(not isinstance(item, dict) for item in attempts)
    ):
        raise ResumeLockError("parent OpenAI journal is not completely resumable")
    openai_call_cap = _positive(openai_call_cap, "openai_call_cap")
    openai_token_cap = _positive(openai_token_cap, "openai_token_cap")
    if openai_journal.get("cap") != openai_call_cap or openai_journal.get("token_cap") != openai_token_cap:
        raise ResumeLockError("parent OpenAI journal caps do not match the resume dispatch")
    usage_keys = {
        "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens",
        "reasoning_tokens",
    }
    totals = openai_journal.get("usage_totals")
    recomputed = {key: 0 for key in usage_keys}
    if not isinstance(totals, dict) or set(totals) != usage_keys:
        raise ResumeLockError("parent OpenAI journal usage totals are invalid")
    for attempt in attempts:
        usage = attempt.get("usage")
        if not isinstance(usage, dict) or set(usage) != usage_keys:
            raise ResumeLockError("parent OpenAI attempt usage is incomplete")
        for key in usage_keys:
            value = usage[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ResumeLockError("parent OpenAI attempt usage is invalid")
            recomputed[key] += value
    if recomputed != totals or totals["total_tokens"] > openai_token_cap:
        raise ResumeLockError("parent OpenAI journal usage does not reconcile")
    if topic_input.get("daily_plan_sha256") != parent_lease["source_bindings"]["daily_plan_sha256"]:
        raise ResumeLockError("topic input is not bound to the parent daily plan")
    for label, review in (("producer", producer_review), ("critic", critic_review)):
        if (
            review.get("daily_plan_sha256") != topic_input.get("daily_plan_sha256")
            or not isinstance(review.get("results"), list)
            or not review["results"]
        ):
            raise ResumeLockError(f"parent {label} review is not bound to the daily plan")
    normalized_head = str(head_sha or "").strip().lower()
    normalized_repo = str(repository or "").strip()
    if not HEAD_SHA_RE.fullmatch(normalized_head):
        raise ResumeLockError("resume head_sha is invalid")
    if not REPOSITORY_RE.fullmatch(normalized_repo):
        raise ResumeLockError("resume repository is invalid")
    lease = {
        "schema_version": SCHEMA,
        "repository": normalized_repo,
        "workflow_path": WORKFLOW_PATH,
        "parent_run_id": parent_run_id,
        "parent_spend_lease_sha256": canonical_hash(parent_lease),
        "parent_topic_input_sha256": canonical_hash(topic_input),
        "parent_producer_review_sha256": canonical_hash(producer_review),
        "parent_critic_review_sha256": canonical_hash(critic_review),
        "parent_openai_journal_sha256": canonical_hash(openai_journal),
        "parent_resume_lease_sha256": (
            canonical_hash(parent_resume_lease) if parent_resume_lease is not None else None
        ),
        "parent_completed_openai_attempts": len(attempts),
        "run_id": _positive(run_id, "run_id"),
        "run_attempt": _positive(run_attempt, "run_attempt"),
        "head_sha": normalized_head,
        "caps": {
            "openai_call_cap": openai_call_cap,
            "openai_token_cap": openai_token_cap,
            "image_call_cap": _positive(image_call_cap, "image_call_cap"),
            "ai33_call_cap": _positive(ai33_call_cap, "ai33_call_cap"),
        },
        "publication_authorized": False,
    }
    lease["resume_lease_sha256"] = self_hash(lease)
    return lease


def validate_resume_lease(
    lease: dict[str, Any], *, repository: str, run_id: int | None = None,
    run_attempt: int | None = None, head_sha: str | None = None,
    parent_run_id: int | None = None,
) -> None:
    if lease.get("schema_version") != SCHEMA:
        raise ResumeLockError("resume lease schema mismatch")
    if lease.get("repository") != repository or lease.get("workflow_path") != WORKFLOW_PATH:
        raise ResumeLockError("resume lease repository/workflow mismatch")
    if lease.get("publication_authorized") is not False:
        raise ResumeLockError("resume lease must not authorize publication")
    claimed = str(lease.get("resume_lease_sha256") or "")
    if not SHA256_RE.fullmatch(claimed) or self_hash(lease) != claimed:
        raise ResumeLockError("resume lease self hash mismatch")
    for field in (
        "parent_spend_lease_sha256", "parent_topic_input_sha256",
        "parent_producer_review_sha256", "parent_critic_review_sha256",
        "parent_openai_journal_sha256",
    ):
        if not SHA256_RE.fullmatch(str(lease.get(field) or "")):
            raise ResumeLockError(f"resume lease {field} is invalid")
    parent_resume_hash = lease.get("parent_resume_lease_sha256")
    if parent_resume_hash is not None and not SHA256_RE.fullmatch(str(parent_resume_hash)):
        raise ResumeLockError("resume lease parent_resume_lease_sha256 is invalid")
    if run_id is not None and lease.get("run_id") != _positive(run_id, "run_id"):
        raise ResumeLockError("resume lease current run mismatch")
    if run_attempt is not None and lease.get("run_attempt") != _positive(run_attempt, "run_attempt"):
        raise ResumeLockError("resume lease run attempt mismatch")
    if head_sha is not None and lease.get("head_sha") != str(head_sha).strip().lower():
        raise ResumeLockError("resume lease head_sha mismatch")
    if parent_run_id is not None and lease.get("parent_run_id") != _positive(parent_run_id, "parent_run_id"):
        raise ResumeLockError("resume lease parent run mismatch")
    if isinstance(lease.get("parent_completed_openai_attempts"), bool) or not isinstance(
        lease.get("parent_completed_openai_attempts"), int
    ) or lease["parent_completed_openai_attempts"] < 1:
        raise ResumeLockError("resume lease completed attempt count is invalid")
    caps = lease.get("caps")
    expected_caps = {
        "openai_call_cap", "openai_token_cap", "image_call_cap", "ai33_call_cap",
    }
    if not isinstance(caps, dict) or set(caps) != expected_caps:
        raise ResumeLockError("resume lease cap contract is invalid")
    for field in expected_caps:
        _positive(caps[field], field)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--existing-root", required=True)
    create.add_argument("--parent-lease", required=True)
    create.add_argument("--topic-input", required=True)
    create.add_argument("--producer-review", required=True)
    create.add_argument("--critic-review", required=True)
    create.add_argument("--openai-journal", required=True)
    create.add_argument("--parent-resume-lease")
    create.add_argument("--parent-run-id", required=True, type=int)
    create.add_argument("--run-id", required=True, type=int)
    create.add_argument("--run-attempt", required=True, type=int)
    create.add_argument("--head-sha", required=True)
    create.add_argument("--repository", required=True)
    create.add_argument("--openai-call-cap", required=True, type=int)
    create.add_argument("--openai-token-cap", required=True, type=int)
    create.add_argument("--image-call-cap", required=True, type=int)
    create.add_argument("--ai33-call-cap", required=True, type=int)
    create.add_argument("--output", required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    inspected = scan_existing(
        Path(args.existing_root), parent_run_id=args.parent_run_id,
        repository=args.repository,
    )
    lease = build_resume_lease(
        parent_lease=read_object(Path(args.parent_lease), "parent lease"),
        topic_input=read_object(Path(args.topic_input), "topic input"),
        producer_review=read_object(Path(args.producer_review), "producer review"),
        critic_review=read_object(Path(args.critic_review), "critic review"),
        openai_journal=read_object(Path(args.openai_journal), "OpenAI journal"),
        parent_run_id=args.parent_run_id, run_id=args.run_id,
        run_attempt=args.run_attempt, head_sha=args.head_sha,
        repository=args.repository, openai_call_cap=args.openai_call_cap,
        openai_token_cap=args.openai_token_cap, image_call_cap=args.image_call_cap,
        ai33_call_cap=args.ai33_call_cap,
        parent_resume_lease=(
            read_object(Path(args.parent_resume_lease), "parent resume lease")
            if args.parent_resume_lease else None
        ),
    )
    atomic_json(Path(args.output), lease)
    print(json.dumps({
        "status": "RESUME_LEASE_CREATED", "inspected_existing_leases": inspected,
        "parent_run_id": lease["parent_run_id"], "run_id": lease["run_id"],
        "resume_lease_sha256": lease["resume_lease_sha256"],
        "publication_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ResumeLockError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
