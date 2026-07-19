"""Fail-closed rights evidence for one exact acc1 episode plan.

The manifest records only safe metadata and hashes.  Agreement text, personal
data, credentials, and other sensitive evidence stay in the operator's
approved storage and are referenced by an opaque locator plus SHA-256.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

from acc1_episode_manifest import canonical_hash, validate_episode_manifest


RIGHTS_MANIFEST_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ELIGIBLE_RIGHTS_STATUSES = {
    "submitted_with_permission",
    "licensed",
    "verified_open_license",
}
ALLOWED_EXCLUSIVITY = {"exclusive", "non_exclusive", "not_applicable"}
ALLOWED_YOUTUBE_SCOPES = {"private", "unlisted", "public"}
REQUIRED_PERMISSION_FIELDS = (
    "commercial_use_allowed",
    "translation_allowed",
    "adaptation_allowed",
    "narration_allowed",
    "audiovisual_sync_allowed",
    "youtube_distribution_allowed",
)


class Acc1RightsManifestError(RuntimeError):
    """Raised when a rights artifact cannot be constructed safely."""


def _source_queue_entries(source_queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = source_queue.get("entries")
    if not isinstance(entries, list):
        raise Acc1RightsManifestError("source queue entries must be a list")
    indexed: dict[str, dict[str, Any]] = {}
    for value in entries:
        if not isinstance(value, dict):
            raise Acc1RightsManifestError("source queue entries must be objects")
        source_id = str(value.get("post_id") or value.get("source_id") or "").strip()
        if not source_id or source_id in indexed:
            raise Acc1RightsManifestError("source queue post ids must be present and unique")
        indexed[source_id] = value
    return indexed


def _queue_source(queue_entry: dict[str, Any], plan_source: dict[str, Any]) -> dict[str, str]:
    source_id = str(plan_source.get("post_id") or "").strip()
    body_sha256 = str(plan_source.get("body_sha256") or "").strip().lower()
    recorded_sha256 = str(
        queue_entry.get("source_body_sha256")
        or queue_entry.get("body_sha256")
        or ""
    ).strip().lower()
    if not SHA256_RE.fullmatch(body_sha256) or recorded_sha256 != body_sha256:
        raise Acc1RightsManifestError(
            f"source queue body checksum does not match episode plan for {source_id!r}",
        )
    author = str(queue_entry.get("author") or "").strip()
    source_url = str(
        queue_entry.get("source_url") or queue_entry.get("url") or ""
    ).strip()
    return {
        "source_id": source_id,
        "source_body_sha256": body_sha256,
        "source_url": source_url,
        "source_author": author,
    }


def build_rights_template(
    episode_plan: dict[str, Any],
    source_queue: dict[str, Any],
) -> dict[str, Any]:
    """Build a checksum-bound template that cannot pass without human input."""

    plan_validation = validate_episode_manifest(episode_plan)
    if plan_validation.get("status") != "PASS":
        raise Acc1RightsManifestError(
            "episode plan is invalid: "
            + "; ".join(plan_validation.get("failures") or []),
        )
    indexed = _source_queue_entries(source_queue)
    sources: list[dict[str, Any]] = []
    for plan_source in episode_plan["sources"]:
        source_id = str(plan_source["post_id"])
        queue_entry = indexed.get(source_id)
        if queue_entry is None:
            raise Acc1RightsManifestError(
                f"episode-plan source {source_id!r} is missing from source queue",
            )
        exact = _queue_source(queue_entry, plan_source)
        sources.append({
            **exact,
            "rightsholder_name": None,
            "rights_status": "discovery_only",
            "evidence_locator": None,
            "evidence_sha256": None,
            "commercial_use_allowed": False,
            "translation_allowed": False,
            "adaptation_allowed": False,
            "narration_allowed": False,
            "audiovisual_sync_allowed": False,
            "youtube_distribution_allowed": False,
            "youtube_scopes": [],
            "territory": None,
            "term": None,
            "exclusivity": None,
            "payment_terms": None,
            "required_credit": None,
            "cleared_by": None,
            "cleared_at": None,
        })
    manifest: dict[str, Any] = {
        "version": RIGHTS_MANIFEST_VERSION,
        "status": "BLOCKED_PENDING_RIGHTS",
        "publication_authorized": False,
        "episode_key": episode_plan["episode_key"],
        "episode_plan_sha256": episode_plan["episode_plan_sha256"],
        "reviewer": None,
        "reviewed_at": None,
        "notes": "",
        "sources": sources,
    }
    manifest["rights_manifest_sha256"] = canonical_hash(manifest)
    return manifest


def _manifest_without_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(manifest)
    value.pop("rights_manifest_sha256", None)
    return value


def validate_rights_manifest(
    manifest: dict[str, Any],
    *,
    episode_plan: dict[str, Any],
    source_queue: dict[str, Any],
    required_youtube_scope: str = "private",
) -> dict[str, Any]:
    """Validate exact source rights without granting publication authority."""

    failures: list[str] = []
    warnings: list[str] = []
    if required_youtube_scope not in ALLOWED_YOUTUBE_SCOPES:
        raise Acc1RightsManifestError("unsupported YouTube rights scope")
    plan_validation = validate_episode_manifest(episode_plan)
    if plan_validation.get("status") != "PASS":
        failures.extend(
            f"episode plan: {failure}"
            for failure in plan_validation.get("failures") or []
        )
    if manifest.get("version") != RIGHTS_MANIFEST_VERSION:
        failures.append("rights manifest version is unsupported")
    if manifest.get("status") != "PASS":
        failures.append("rights manifest status must PASS")
    if manifest.get("publication_authorized") is not False:
        failures.append("rights manifest publication_authorized must remain false")
    if manifest.get("episode_key") != episode_plan.get("episode_key"):
        failures.append("rights manifest episode_key does not match episode plan")
    if manifest.get("episode_plan_sha256") != episode_plan.get("episode_plan_sha256"):
        failures.append("rights manifest is not bound to the immutable episode plan")
    recorded_hash = str(manifest.get("rights_manifest_sha256") or "").lower()
    if not SHA256_RE.fullmatch(recorded_hash):
        failures.append("rights_manifest_sha256 must be a lowercase SHA-256")
    elif recorded_hash != canonical_hash(_manifest_without_hash(manifest)):
        failures.append("rights_manifest_sha256 does not match manifest content")
    if not str(manifest.get("reviewer") or "").strip():
        failures.append("rights reviewer is required")
    if not str(manifest.get("reviewed_at") or "").strip():
        failures.append("rights reviewed_at is required")

    try:
        indexed = _source_queue_entries(source_queue)
    except Acc1RightsManifestError as exc:
        indexed = {}
        failures.append(str(exc))
    expected_sources = episode_plan.get("sources")
    rights_sources = manifest.get("sources")
    if not isinstance(expected_sources, list) or not expected_sources:
        failures.append("episode plan has no exact sources")
        expected_sources = []
    if not isinstance(rights_sources, list):
        failures.append("rights manifest sources must be a list")
        rights_sources = []
    expected_ids = [str(item.get("post_id") or "") for item in expected_sources]
    actual_ids = [
        str(item.get("source_id") or "") if isinstance(item, dict) else ""
        for item in rights_sources
    ]
    if actual_ids != expected_ids:
        failures.append("rights manifest sources must exactly match episode-plan order")
    if len(actual_ids) != len(set(actual_ids)):
        failures.append("rights manifest source ids must be unique")

    for index, plan_source in enumerate(expected_sources):
        source_id = str(plan_source.get("post_id") or "")
        if index >= len(rights_sources) or not isinstance(rights_sources[index], dict):
            failures.append(f"rights record is missing for source {source_id!r}")
            continue
        record = rights_sources[index]
        queue_entry = indexed.get(source_id)
        if queue_entry is None:
            failures.append(f"source queue entry is missing for {source_id!r}")
            continue
        try:
            exact = _queue_source(queue_entry, plan_source)
        except Acc1RightsManifestError as exc:
            failures.append(str(exc))
            continue
        for field in ("source_id", "source_body_sha256", "source_url", "source_author"):
            if str(record.get(field) or "") != exact[field]:
                failures.append(f"rights record {field} mismatch for source {source_id!r}")
        if not exact["source_author"]:
            failures.append(f"source author is required for rights clearance: {source_id!r}")
        if not exact["source_url"]:
            failures.append(f"source URL is required for rights clearance: {source_id!r}")
        if str(record.get("rights_status") or "") not in ELIGIBLE_RIGHTS_STATUSES:
            failures.append(f"source rights_status is not distribution-eligible: {source_id!r}")
        if not str(record.get("rightsholder_name") or "").strip():
            failures.append(f"rightsholder_name is required: {source_id!r}")
        if not str(record.get("evidence_locator") or "").strip():
            failures.append(f"rights evidence_locator is required: {source_id!r}")
        if not SHA256_RE.fullmatch(str(record.get("evidence_sha256") or "").lower()):
            failures.append(f"rights evidence_sha256 is required: {source_id!r}")
        for field in REQUIRED_PERMISSION_FIELDS:
            if record.get(field) is not True:
                failures.append(f"rights permission {field} must be true: {source_id!r}")
        scopes = record.get("youtube_scopes")
        if not isinstance(scopes, list) or any(
            scope not in ALLOWED_YOUTUBE_SCOPES for scope in scopes
        ):
            failures.append(f"youtube_scopes are invalid: {source_id!r}")
        elif required_youtube_scope not in scopes:
            failures.append(
                f"rights do not include YouTube {required_youtube_scope}: {source_id!r}",
            )
        for field in (
            "territory", "term", "payment_terms", "required_credit",
            "cleared_by", "cleared_at",
        ):
            if not str(record.get(field) or "").strip():
                failures.append(f"rights field {field} is required: {source_id!r}")
        if str(record.get("exclusivity") or "") not in ALLOWED_EXCLUSIVITY:
            failures.append(f"rights exclusivity is invalid: {source_id!r}")
    if not str(manifest.get("notes") or "").strip():
        warnings.append("rights manifest notes are empty")
    return {
        "version": RIGHTS_MANIFEST_VERSION,
        "status": "PASS" if not failures else "BLOCKED",
        "publication_authorized": False,
        "episode_plan_sha256": episode_plan.get("episode_plan_sha256"),
        "rights_manifest_sha256": recorded_hash or None,
        "required_youtube_scope": required_youtube_scope,
        "failures": failures,
        "warnings": warnings,
    }


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Acc1RightsManifestError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser("template")
    template.add_argument("--episode-plan", required=True)
    template.add_argument("--source-queue", required=True)
    template.add_argument("--output", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--episode-plan", required=True)
    validate.add_argument("--source-queue", required=True)
    validate.add_argument("--rights-manifest", required=True)
    validate.add_argument(
        "--required-youtube-scope",
        choices=tuple(sorted(ALLOWED_YOUTUBE_SCOPES)),
        default="private",
    )
    validate.add_argument("--output", required=True)
    args = parser.parse_args()
    episode_plan = _load_object(Path(args.episode_plan))
    source_queue = _load_object(Path(args.source_queue))
    if args.command == "template":
        payload = build_rights_template(episode_plan, source_queue)
        exit_code = 0
    else:
        payload = validate_rights_manifest(
            _load_object(Path(args.rights_manifest)),
            episode_plan=episode_plan,
            source_queue=source_queue,
            required_youtube_scope=args.required_youtube_scope,
        )
        exit_code = 0 if payload["status"] == "PASS" else 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, Acc1RightsManifestError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
