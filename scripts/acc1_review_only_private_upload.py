#!/usr/bin/env python3
"""Prepare and verify one acc1 private upload used only for human review.

This adapter intentionally sits before the rights/release gate.  It verifies a
successful factory artifact, derives clearly marked review metadata, and
validates the uploader receipt.  It never authorizes publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_FACTORY_WORKFLOW = "acc1 Daily Episode Factory"
EXPECTED_ACC1_CHANNEL_ID = "UCNSxg53AGM4WstRjGiQdS8w"
EXPECTED_ACC1_HANDLE = "@ChonkerTalksRussia"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[1-9][0-9]*$")
HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UPLOAD_ARTIFACTS = {
    "video_sha256": "final-output.mp4",
    "thumbnail_sha256": "youtube-thumbnail.png",
    "metadata_sha256": "youtube-metadata.json",
}
REVIEW_TITLE_PREFIX = "[ПРОСМОТР] "
REVIEW_DESCRIPTION_PREFIX = (
    "СЛУЖЕБНАЯ PRIVATE-КОПИЯ ДЛЯ ПРОСМОТРА. НЕ ПУБЛИКОВАТЬ."
)


class ReviewOnlyUploadError(RuntimeError):
    """Raised when review-only evidence is incomplete or inconsistent."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewOnlyUploadError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReviewOnlyUploadError(f"{path} must contain a JSON object")
    return value


def canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    if not path.is_file():
        raise ReviewOnlyUploadError(f"required artifact is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hashed_json(
    path: Path,
    payload: dict[str, Any],
    hash_field: str,
) -> dict[str, Any]:
    output = dict(payload)
    output[hash_field] = canonical_hash(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return output


def verify_self_hash(
    payload: dict[str, Any],
    hash_field: str,
    label: str,
) -> str:
    embedded = str(payload.get(hash_field) or "").strip().lower()
    unhashed = dict(payload)
    unhashed.pop(hash_field, None)
    if not SHA256_RE.fullmatch(embedded):
        raise ReviewOnlyUploadError(f"{label} has invalid {hash_field}")
    if embedded != canonical_hash(unhashed):
        raise ReviewOnlyUploadError(f"{label} self hash does not match")
    return embedded


def verify_source_run(
    source_run: dict[str, Any],
    *,
    source_run_id: str,
    expected_branch: str,
) -> None:
    if not RUN_ID_RE.fullmatch(source_run_id):
        raise ReviewOnlyUploadError("source_run_id must be a positive GitHub run id")
    if source_run.get("workflowName") != EXPECTED_FACTORY_WORKFLOW:
        raise ReviewOnlyUploadError("source run is not the acc1 Daily Episode Factory")
    if source_run.get("conclusion") != "success":
        raise ReviewOnlyUploadError("source factory run did not succeed")
    if source_run.get("event") != "workflow_dispatch":
        raise ReviewOnlyUploadError("source factory run was not manually dispatched")
    if source_run.get("headBranch") != expected_branch:
        raise ReviewOnlyUploadError("source factory run is not from the default branch")
    if not HEAD_SHA_RE.fullmatch(str(source_run.get("headSha") or "")):
        raise ReviewOnlyUploadError("source factory run head SHA is invalid")


def expected_channel_config(channels_path: Path) -> dict[str, Any]:
    channels = load_object(channels_path).get("channels")
    if not isinstance(channels, list):
        raise ReviewOnlyUploadError("channels.json must contain a channels list")
    matches = [
        item
        for item in channels
        if isinstance(item, dict) and item.get("id") == "acc1"
    ]
    if len(matches) != 1:
        raise ReviewOnlyUploadError("channels.json must contain exactly one acc1 row")
    channel = matches[0]
    if channel.get("handle") != EXPECTED_ACC1_HANDLE:
        raise ReviewOnlyUploadError("acc1 handle does not match the review target")
    if channel.get("videos_per_day") != 0:
        raise ReviewOnlyUploadError("acc1 publishing hold must remain active")
    if channel.get("automation_enabled") is not False:
        raise ReviewOnlyUploadError("acc1 automation must remain disabled")
    return channel


def prepare_review_upload(
    *,
    artifact_root: Path,
    source_run_path: Path,
    source_run_id: str,
    expected_branch: str,
    channels_path: Path,
    metadata_output: Path,
    contract_output: Path,
) -> dict[str, Any]:
    root = artifact_root.resolve()
    if not root.is_dir():
        raise ReviewOnlyUploadError("factory artifact root is missing")

    source_run = load_object(source_run_path)
    verify_source_run(
        source_run,
        source_run_id=source_run_id,
        expected_branch=expected_branch,
    )
    expected_channel_config(channels_path)

    result = load_object(root / "factory-result.json")
    manifest = load_object(root / "release-candidate-manifest.json")
    media_qa = load_object(root / "media-qa.json")
    episode_plan = load_object(root / "episode-plan.json")

    if result.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise ReviewOnlyUploadError("factory result is not READY_FOR_HUMAN_REVIEW")
    if result.get("publication_authorized") is not False:
        raise ReviewOnlyUploadError("factory result publication boundary drifted")
    if manifest.get("version") != 2:
        raise ReviewOnlyUploadError("factory release manifest version must be 2")
    if manifest.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise ReviewOnlyUploadError("factory release manifest is not review-ready")
    if manifest.get("publication_authorized") is not False:
        raise ReviewOnlyUploadError("factory release manifest authorizes publication")
    if manifest.get("performance_outcome_guaranteed") is not False:
        raise ReviewOnlyUploadError("factory release manifest guarantees performance")
    if manifest.get("media_qa_status") != "PASS":
        raise ReviewOnlyUploadError("factory release manifest media QA did not pass")
    if manifest.get("creative_review_status") != "BLOCKED_PENDING_HUMAN":
        raise ReviewOnlyUploadError("factory artifact no longer awaits human review")

    manifest_hash = verify_self_hash(
        manifest,
        "release_candidate_manifest_sha256",
        "release candidate manifest",
    )
    if result.get("release_candidate_manifest_sha256") != manifest_hash:
        raise ReviewOnlyUploadError("factory result is bound to another release manifest")

    plan_hash = verify_self_hash(
        episode_plan,
        "episode_plan_sha256",
        "episode plan",
    )
    if result.get("episode_plan_sha256") != plan_hash:
        raise ReviewOnlyUploadError("factory result is bound to another episode plan")
    if manifest.get("episode_plan_sha256") != plan_hash:
        raise ReviewOnlyUploadError("release manifest is bound to another episode plan")

    claimed_artifacts = manifest.get("artifact_sha256")
    if not isinstance(claimed_artifacts, dict):
        raise ReviewOnlyUploadError("release manifest artifact hash map is missing")
    actual_artifacts: dict[str, str] = {}
    for field, filename in UPLOAD_ARTIFACTS.items():
        claimed = str(claimed_artifacts.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(claimed):
            raise ReviewOnlyUploadError(f"release manifest has invalid {field}")
        actual = file_hash(root / filename)
        if actual != claimed:
            raise ReviewOnlyUploadError(f"factory upload artifact hash mismatch: {field}")
        actual_artifacts[field] = actual

    claimed_evidence = manifest.get("evidence_sha256")
    if not isinstance(claimed_evidence, dict):
        raise ReviewOnlyUploadError("release manifest evidence hash map is missing")
    if claimed_evidence.get("media_qa") != file_hash(root / "media-qa.json"):
        raise ReviewOnlyUploadError("factory media QA evidence hash mismatch")
    if media_qa.get("status") != "PASS" or media_qa.get("failures"):
        raise ReviewOnlyUploadError("media-qa.json does not pass")
    if media_qa.get("publication_authorized") is not False:
        raise ReviewOnlyUploadError("media-qa.json publication boundary drifted")
    media_hashes = media_qa.get("artifact_sha256")
    if not isinstance(media_hashes, dict):
        raise ReviewOnlyUploadError("media-qa.json artifact hash map is missing")
    for field, actual in actual_artifacts.items():
        if media_hashes.get(field) != actual:
            raise ReviewOnlyUploadError(f"media QA is bound to another {field}")

    metadata = load_object(root / "youtube-metadata.json")
    original_title = str(metadata.get("youtube_title") or "").strip()
    original_description = str(metadata.get("youtube_description") or "").strip()
    if not original_title:
        raise ReviewOnlyUploadError("YouTube metadata title is empty")
    if not original_description:
        raise ReviewOnlyUploadError("YouTube metadata description is empty")
    if str(metadata.get("language") or "").strip().lower() != "ru":
        raise ReviewOnlyUploadError("YouTube metadata language must be ru")

    title_room = 100 - len(REVIEW_TITLE_PREFIX)
    review_metadata = dict(metadata)
    review_metadata["youtube_title"] = (
        REVIEW_TITLE_PREFIX + original_title[:title_room]
    )
    review_metadata["youtube_description"] = (
        f"{REVIEW_DESCRIPTION_PREFIX}\n\n{original_description}"
    )[:5000]
    review_metadata["review_only"] = True
    review_metadata["publication_authorized"] = False
    review_metadata["source_run_id"] = source_run_id
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(
            review_metadata,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    review_metadata_hash = file_hash(metadata_output)

    contract = {
        "version": 1,
        "status": "READY_FOR_REVIEW_ONLY_PRIVATE_UPLOAD",
        "review_only": True,
        "publication_authorized": False,
        "scheduling_authorized": False,
        "provider_calls_authorized": False,
        "source_run": {
            "run_id": source_run_id,
            "workflow_name": EXPECTED_FACTORY_WORKFLOW,
            "head_branch": source_run["headBranch"],
            "head_sha": source_run["headSha"],
            "artifact_name": f"acc1-daily-episode-{source_run_id}",
        },
        "target": {
            "account_id": "acc1",
            "account_index": "1",
            "youtube_channel_id": EXPECTED_ACC1_CHANNEL_ID,
            "youtube_handle": EXPECTED_ACC1_HANDLE,
            "privacy_status": "private",
        },
        "episode_plan_sha256": plan_hash,
        "release_candidate_manifest_sha256": manifest_hash,
        "artifact_sha256": actual_artifacts,
        "review_metadata_sha256": review_metadata_hash,
    }
    return write_hashed_json(
        contract_output,
        contract,
        "review_upload_contract_sha256",
    )


def verify_upload_receipt(
    *,
    contract_path: Path,
    receipt_path: Path,
    upload_run_id: str,
    result_output: Path,
) -> dict[str, Any]:
    if not RUN_ID_RE.fullmatch(upload_run_id):
        raise ReviewOnlyUploadError("upload_run_id must be a positive GitHub run id")
    contract = load_object(contract_path)
    contract_hash = verify_self_hash(
        contract,
        "review_upload_contract_sha256",
        "review upload contract",
    )
    if contract.get("status") != "READY_FOR_REVIEW_ONLY_PRIVATE_UPLOAD":
        raise ReviewOnlyUploadError("review upload contract is not ready")
    if contract.get("review_only") is not True:
        raise ReviewOnlyUploadError("review upload contract scope drifted")
    for field in (
        "publication_authorized",
        "scheduling_authorized",
        "provider_calls_authorized",
    ):
        if contract.get(field) is not False:
            raise ReviewOnlyUploadError(f"review upload contract authorizes {field}")

    receipt = load_object(receipt_path)
    target = contract.get("target") or {}
    artifacts = contract.get("artifact_sha256") or {}
    if receipt.get("status") != "COMPLETE":
        raise ReviewOnlyUploadError("YouTube upload receipt is incomplete")
    if receipt.get("privacy_status_requested") != "private":
        raise ReviewOnlyUploadError("YouTube upload did not request private status")
    if receipt.get("privacy_status_readback") != "private":
        raise ReviewOnlyUploadError("YouTube readback is not private")
    if receipt.get("channel_id") != target.get("youtube_channel_id"):
        raise ReviewOnlyUploadError("YouTube readback resolved to another channel")
    if receipt.get("thumbnail_uploaded") is not True:
        raise ReviewOnlyUploadError("review thumbnail was not uploaded")
    if receipt.get("caption_uploaded") is not False:
        raise ReviewOnlyUploadError("review-only upload unexpectedly mutated captions")
    if receipt.get("video_sha256") != artifacts.get("video_sha256"):
        raise ReviewOnlyUploadError("uploaded video hash does not match the factory")
    if receipt.get("thumbnail_sha256") != artifacts.get("thumbnail_sha256"):
        raise ReviewOnlyUploadError("uploaded thumbnail hash does not match the factory")
    video_id = str(receipt.get("video_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", video_id):
        raise ReviewOnlyUploadError("YouTube receipt video id is invalid")

    result = {
        "version": 1,
        "status": "PRIVATE_REVIEW_UPLOAD_VERIFIED",
        "review_only": True,
        "publication_authorized": False,
        "scheduling_authorized": False,
        "source_run_id": contract["source_run"]["run_id"],
        "upload_run_id": upload_run_id,
        "review_upload_contract_sha256": contract_hash,
        "upload_receipt_sha256": file_hash(receipt_path),
        "video_id": video_id,
        "channel_id": receipt["channel_id"],
        "privacy_status": "private",
        "video_sha256": receipt["video_sha256"],
        "thumbnail_sha256": receipt["thumbnail_sha256"],
    }
    return write_hashed_json(
        result_output,
        result,
        "review_upload_result_sha256",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or verify one acc1 review-only private upload.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--artifact-root", type=Path, required=True)
    prepare.add_argument("--source-run", type=Path, required=True)
    prepare.add_argument("--source-run-id", required=True)
    prepare.add_argument("--expected-branch", required=True)
    prepare.add_argument("--channels", type=Path, default=Path("channels.json"))
    prepare.add_argument("--metadata-output", type=Path, required=True)
    prepare.add_argument("--contract-output", type=Path, required=True)

    verify = subparsers.add_parser("verify-receipt")
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--upload-run-id", required=True)
    verify.add_argument("--result-output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare":
            prepare_review_upload(
                artifact_root=args.artifact_root,
                source_run_path=args.source_run,
                source_run_id=args.source_run_id,
                expected_branch=args.expected_branch,
                channels_path=args.channels,
                metadata_output=args.metadata_output,
                contract_output=args.contract_output,
            )
        else:
            verify_upload_receipt(
                contract_path=args.contract,
                receipt_path=args.receipt,
                upload_run_id=args.upload_run_id,
                result_output=args.result_output,
            )
    except ReviewOnlyUploadError as exc:
        raise SystemExit(f"review-only upload blocked: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
