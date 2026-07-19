"""Fail-closed artifact release gate for an acc1 review candidate.

This gate deliberately does not authorize publication.  It joins the separate
source/editorial, technical-media, thumbnail and human creative-review evidence
into checksum-bound legacy or daily-factory review decisions.  Neither path
authorizes an upload or publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from acc1_episode_manifest import canonical_hash, validate_episode_manifest
from acc1_rights_manifest import validate_rights_manifest
from acc1_visual_contract import (
    CINEMATIC_STORY_MODE,
    EDITORIAL_MOTION_MODE,
    resolve_visual_mode,
)
from scripts.build_acc1_creative_review_template import checks_for_mode


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT_HASH_FIELDS = (
    "script_sha256",
    "audio_sha256",
    "metadata_sha256",
    "storyboard_sha256",
    "video_sha256",
    "thumbnail_sha256",
)
REQUIRED_CREATIVE_CHECKS = (
    "editorial_acceptance",
    "voice_role_confirmed",
    "first_30_seconds_accepted",
    "text_readability_accepted",
    "visual_rhythm_accepted",
    "reddit_ui_sequence_accepted",
    "background_character_accepted",
    "source_visual_blend_accepted",
    "thumbnail_truthful",
    "fiction_disclosure_accepted",
)
FACTORY_ARTIFACT_PATHS = {
    "script_sha256": "episode-script.json",
    "audio_sha256": "tts/compilation_voice_mix.wav",
    "metadata_sha256": "youtube-metadata.json",
    "storyboard_sha256": "storyboard.json",
    "video_sha256": "final-output.mp4",
    "thumbnail_sha256": "youtube-thumbnail.png",
}
FACTORY_EVIDENCE_PATHS = {
    "daily_plan": "daily-plan.json",
    "source_queue": "source-queue.json",
    "source_review": "source-review.json",
    "candidate_pool": "candidate-pool.json",
    "source_stage": "source-stage.json",
    "spend_lease": "spend-lease.json",
    "paid_preflight": "paid-preflight.json",
    "producer_review": "producer-review.json",
    "critic_review": "critic-review.json",
    "topic_playoff_input": "topic-playoff-input.json",
    "topic_playoff": "topic-playoff.json",
    "episode_greenlight": "episode-greenlight.json",
    "episode_plan": "episode-plan.json",
    "text_layout_report": "text-layout-report.json",
    "runtime_estimate_report": "runtime-estimate-report.json",
    "scene_images_manifest": "scene-images-manifest.json",
    "thumbnail_manifest": "thumbnail-manifest.json",
    "tts_state": "tts/compilation_tts_state.json",
    "pause_map": "tts/narration-pause-map.json",
    "audio_mix_report": "tts/audio-mix-report.json",
    "render_report": "render-report.json",
    "media_qa": "media-qa.json",
    "creative_review": "creative-review.json",
    "gemini_attempts": "provider-attempts/gemini.json",
    "openai_translation_attempts": "provider-attempts/openai-translation.json",
    "image_attempts": "provider-attempts/image.json",
    "ai33_attempts": "provider-attempts/ai33.json",
}
FACTORY_CINEMATIC_EVIDENCE_PATHS = {
    "shot_plan": "shot-plan.json",
    "caption_track": "caption-track.json",
    "caption_srt": "final-output.srt",
}
FACTORY_EDITORIAL_MOTION_EVIDENCE_PATHS = {
    "motion_plan": "motion-plan.json",
    "caption_track": "caption-track.json",
    "caption_srt": "editorial-motion-captions.srt",
}
REQUIRED_CREATIVE_OBSERVATION_CATEGORIES = {
    "first_30_seconds",
    "visual",
    "audio",
}


class Acc1ReleaseGateError(RuntimeError):
    """Raised when an input artifact cannot be read safely."""


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Acc1ReleaseGateError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_hash(value: Any) -> bool:
    return bool(SHA256_RE.fullmatch(str(value or "").strip().lower()))


def _status_passes(value: Any) -> bool:
    return str(value or "").strip().upper() in {"PASS", "OK"}


def validate_release(
    *,
    strategy_report: dict[str, Any],
    greenlight_report: dict[str, Any],
    source_queue: dict[str, Any],
    topic_review: dict[str, Any],
    greenlight: dict[str, Any],
    config: dict[str, Any],
    episode_plan: dict[str, Any],
    media_qa: dict[str, Any],
    thumbnail_manifest: dict[str, Any],
    creative_review: dict[str, Any],
    artifact_sha256: dict[str, str],
) -> dict[str, Any]:
    """Return a deterministic, publication-safe release decision."""

    failures: list[str] = []
    warnings: list[str] = []

    plan_validation = validate_episode_manifest(
        episode_plan,
        source_queue=source_queue,
        topic_review=topic_review,
        greenlight=greenlight,
        config=config,
    )
    if not _status_passes(plan_validation.get("status")):
        failures.extend(
            f"episode plan: {failure}" for failure in plan_validation.get("failures") or []
        )
    episode_plan_sha256 = str(episode_plan.get("episode_plan_sha256") or "").lower()

    normalized_artifacts: dict[str, str] = {}
    if not isinstance(artifact_sha256, dict):
        failures.append("exact artifact checksums are required")
    else:
        for field in ARTIFACT_HASH_FIELDS:
            digest = str(artifact_sha256.get(field) or "").strip().lower()
            if not _valid_hash(digest):
                failures.append(f"artifact_sha256.{field} must be a SHA-256 digest")
            else:
                normalized_artifacts[field] = digest
    final_video_sha256 = normalized_artifacts.get("video_sha256", "")
    thumbnail_sha256 = normalized_artifacts.get("thumbnail_sha256", "")

    channel_strategy = strategy_report.get("channel_strategy") or strategy_report
    if not _status_passes(channel_strategy.get("status")):
        failures.append("channel strategy must PASS")

    source_plan = strategy_report.get("source_plan")
    if not isinstance(source_plan, dict) or not _status_passes(source_plan.get("status")):
        failures.append("exact pilot source plan must PASS")

    episode_greenlight = greenlight_report.get("episode_greenlight") or greenlight_report
    if not _status_passes(episode_greenlight.get("status")):
        failures.append("episode greenlight must PASS")
    if episode_greenlight.get("publication_authorized") is not False:
        failures.append("release evidence publication_authorized must be false")
    if episode_greenlight.get("artifact_bindings_verified") is not True:
        failures.append("episode greenlight artifact bindings must be verified against exact artifacts")
    if episode_greenlight.get("selected_source_verified") is not True:
        failures.append("episode greenlight selected source must be verified")
    if isinstance(source_plan, dict) and source_plan.get("pilot_id") != episode_greenlight.get("pilot_id"):
        failures.append("strategy source plan and episode greenlight pilot_id must match")
    if isinstance(source_plan, dict) and source_plan.get("format") != episode_greenlight.get("format"):
        failures.append("strategy source plan and episode greenlight format must match")
    if isinstance(source_plan, dict) and source_plan.get("pillar") != episode_greenlight.get("pillar"):
        failures.append("strategy source plan and episode greenlight pillar must match")
    for field in ("pilot_id", "format", "pillar"):
        if episode_greenlight.get(field) != episode_plan.get(field):
            failures.append(f"episode greenlight report and episode plan {field} must match")

    bindings = episode_greenlight.get("artifact_bindings")
    if not isinstance(bindings, dict):
        failures.append("episode greenlight artifact_bindings are required")
        bindings = {}
    for field in ("source_sha256", "review_sha256"):
        if not _valid_hash(bindings.get(field)):
            failures.append(f"artifact_bindings.{field} must be a SHA-256 digest")
    if bindings != greenlight.get("artifact_bindings"):
        failures.append("episode greenlight report bindings do not match exact greenlight artifact")
    for field in ("pilot_id", "pillar"):
        if episode_greenlight.get(field) != greenlight.get(field):
            failures.append(f"episode greenlight report {field} does not match exact greenlight artifact")
    if str(episode_greenlight.get("format") or "").upper() != str(greenlight.get("format") or "").upper():
        failures.append("episode greenlight report format does not match exact greenlight artifact")

    if not _status_passes(media_qa.get("status")):
        failures.append("media QA must PASS")
    if media_qa.get("failures"):
        failures.append("media QA contains failures")
    if media_qa.get("publication_authorized") is not False:
        failures.append("media QA publication_authorized must remain false")
    if media_qa.get("creative_status") not in (None, "PASS"):
        failures.append("media QA creative_status must PASS when present")
    if media_qa.get("expected_voice_id_checked") is not True:
        failures.append("media QA must verify the configured voice id")
    if media_qa.get("episode_plan_sha256") != episode_plan_sha256:
        failures.append("media QA is not bound to the immutable episode plan")
    media_artifacts = media_qa.get("artifact_sha256")
    if not isinstance(media_artifacts, dict):
        failures.append("media QA exact artifact checksums are required")
        media_artifacts = {}
    for field in ARTIFACT_HASH_FIELDS:
        if str(media_artifacts.get(field) or "").lower() != normalized_artifacts.get(field):
            failures.append(f"media QA {field} does not match the exact release artifact")
    if media_qa.get("truth_disclosure_audible") is not True:
        failures.append("media QA must confirm audible truth disclosure")
    if media_qa.get("truth_disclosure_visible_in_metadata") is not True:
        failures.append("media QA must confirm metadata-visible truth disclosure")
    if str(media_qa.get("video_sha256") or "").lower() != final_video_sha256.lower():
        failures.append("media QA is not bound to the final video")
    if str(media_qa.get("thumbnail_sha256") or "").lower() != thumbnail_sha256.lower():
        failures.append("media QA is not bound to the final thumbnail")

    if not _status_passes(thumbnail_manifest.get("status")):
        failures.append("thumbnail manifest must PASS")
    if thumbnail_manifest.get("episode_plan_sha256") != episode_plan_sha256:
        failures.append("thumbnail manifest is not bound to the immutable episode plan")
    manifest_thumbnail_hash = str(thumbnail_manifest.get("sha256") or "").lower()
    if not _valid_hash(manifest_thumbnail_hash):
        failures.append("thumbnail manifest sha256 is required")
    elif manifest_thumbnail_hash != thumbnail_sha256.lower():
        failures.append("thumbnail checksum does not match thumbnail manifest")
    dimensions = thumbnail_manifest.get("dimensions")
    if not (
        isinstance(dimensions, list)
        and len(dimensions) == 2
        and all(isinstance(item, int) and item > 0 for item in dimensions)
        and dimensions[0] * 9 == dimensions[1] * 16
        and dimensions[0] >= 1280
        and dimensions[1] >= 720
    ):
        failures.append("thumbnail must be 16:9 and at least 1280x720")

    if not _valid_hash(final_video_sha256):
        failures.append("final video SHA-256 is required")
    if not _valid_hash(thumbnail_sha256):
        failures.append("thumbnail SHA-256 is required")

    if creative_review.get("status") != "PASS":
        failures.append("creative review must PASS")
    if creative_review.get("publication_authorized") is not False:
        failures.append("creative review publication_authorized must remain false")
    if creative_review.get("episode_plan_sha256") != episode_plan_sha256:
        failures.append("creative review is not bound to the immutable episode plan")
    if str(creative_review.get("video_sha256") or "").lower() != final_video_sha256.lower():
        failures.append("creative review is not bound to the final video")
    if str(creative_review.get("thumbnail_sha256") or "").lower() != thumbnail_sha256.lower():
        failures.append("creative review is not bound to the final thumbnail")
    if not str(creative_review.get("reviewer") or "").strip():
        failures.append("creative review reviewer is required")
    if not str(creative_review.get("reviewed_at") or "").strip():
        failures.append("creative review reviewed_at is required")
    checks = creative_review.get("checks")
    if not isinstance(checks, dict):
        failures.append("creative review checks are required")
        checks = {}
    for field in REQUIRED_CREATIVE_CHECKS:
        if checks.get(field) is not True:
            failures.append(f"creative review check failed: {field}")
    if creative_review.get("notes") in (None, ""):
        warnings.append("creative review notes are empty")

    return {
        "version": 1,
        "status": "READY_FOR_UNLISTED_REVIEW" if not failures else "BLOCKED",
        "publication_authorized": False,
        "episode_plan_sha256": episode_plan_sha256 or None,
        "artifact_sha256": {
            field: normalized_artifacts.get(field) for field in ARTIFACT_HASH_FIELDS
        },
        "failures": failures,
        "warnings": warnings,
        "evidence": {
            "source_sha256": bindings.get("source_sha256"),
            "review_sha256": bindings.get("review_sha256"),
            "episode_plan_sha256": episode_plan_sha256 or None,
            "script_sha256": normalized_artifacts.get("script_sha256"),
            "audio_sha256": normalized_artifacts.get("audio_sha256"),
            "metadata_sha256": normalized_artifacts.get("metadata_sha256"),
            "storyboard_sha256": normalized_artifacts.get("storyboard_sha256"),
            "video_sha256": final_video_sha256,
            "thumbnail_sha256": thumbnail_sha256,
        },
    }


def _verify_claimed_files(
    *,
    root: Path,
    paths: dict[str, str],
    claimed: Any,
    label: str,
    failures: list[str],
) -> dict[str, str]:
    if not isinstance(claimed, dict):
        failures.append(f"factory {label} checksum map is required")
        claimed = {}
    expected_keys = set(paths)
    actual_keys = set(claimed)
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    if missing:
        failures.append(f"factory {label} checksum keys are missing: {', '.join(missing)}")
    if unexpected:
        failures.append(f"factory {label} checksum keys are unexpected: {', '.join(unexpected)}")
    actual_hashes: dict[str, str] = {}
    resolved_root = root.resolve()
    for field, relative in paths.items():
        path = (resolved_root / relative).resolve()
        if path == resolved_root or resolved_root not in path.parents or not path.is_file():
            failures.append(f"factory {label} file is missing: {relative}")
            continue
        digest = sha256_file(path)
        actual_hashes[field] = digest
        if str(claimed.get(field) or "").strip().lower() != digest:
            failures.append(f"factory {label} checksum mismatch: {field}")
    return actual_hashes


def _validate_factory_creative_review(
    review: dict[str, Any],
    *,
    release_manifest: dict[str, Any],
    artifact_hashes: dict[str, str],
) -> list[str]:
    failures: list[str] = []
    visual_mode = str(release_manifest.get("visual_mode") or "")
    try:
        expected_checks = checks_for_mode(visual_mode)
    except ValueError:
        failures.append("factory release manifest visual_mode is invalid")
        expected_checks = ()
    if review.get("version") != 3:
        failures.append("completed creative review version must be 3")
    if review.get("status") != "PASS":
        failures.append("completed creative review status must PASS")
    if review.get("publication_authorized") is not False:
        failures.append("creative review publication_authorized must remain false")
    if review.get("decision_scope") != "private_review_only":
        failures.append("creative review decision_scope must be private_review_only")
    if review.get("human_attested") is not True:
        failures.append("creative review human_attested must be true")
    for field in (
        "episode_plan_sha256",
        "daily_plan_sha256",
        "visual_mode",
        "narration_profile_id",
        "narration_profile_sha256",
        "audio_sha256",
        "pause_map_sha256",
        "audio_mix_report_sha256",
        "shot_plan_sha256",
        "motion_plan_sha256",
        "caption_track_sha256",
    ):
        if review.get(field) != release_manifest.get(field):
            failures.append(f"creative review {field} does not match factory manifest")
    if str(review.get("video_sha256") or "").lower() != artifact_hashes.get("video_sha256"):
        failures.append("creative review is not bound to the exact video")
    if str(review.get("thumbnail_sha256") or "").lower() != artifact_hashes.get("thumbnail_sha256"):
        failures.append("creative review is not bound to the exact thumbnail")
    if not str(review.get("reviewer") or "").strip():
        failures.append("creative review reviewer is required")
    if not str(review.get("reviewed_at") or "").strip():
        failures.append("creative review reviewed_at is required")
    if not str(review.get("notes") or "").strip():
        failures.append("creative review notes are required")
    checks = review.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(expected_checks):
        failures.append("creative review checks do not match the exact visual mode")
    else:
        for field in expected_checks:
            if checks.get(field) is not True:
                failures.append(f"creative review check failed: {field}")
    observations = review.get("observations")
    if not isinstance(observations, list) or not observations:
        failures.append("creative review timestamped observations are required")
        observations = []
    categories: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            failures.append(f"creative review observation {index} must be an object")
            continue
        category = str(observation.get("category") or "").strip()
        timecode = observation.get("timecode_sec")
        note = str(observation.get("observation") or "").strip()
        if category:
            categories.add(category)
        if not isinstance(timecode, (int, float)) or isinstance(timecode, bool) or timecode < 0:
            failures.append(f"creative review observation {index} timecode_sec is invalid")
        if not note:
            failures.append(f"creative review observation {index} text is required")
        if observation.get("verdict") not in {"PASS", "CHANGE", "BLOCKED"}:
            failures.append(f"creative review observation {index} verdict is invalid")
        elif observation.get("verdict") != "PASS":
            failures.append(
                f"creative review observation {index} must PASS for release",
            )
    missing_categories = sorted(REQUIRED_CREATIVE_OBSERVATION_CATEGORIES - categories)
    if missing_categories:
        failures.append(
            "creative review observation categories are missing: "
            + ", ".join(missing_categories),
        )
    return failures


def validate_factory_release(
    *,
    artifact_root: Path,
    creative_review: dict[str, Any],
    creative_review_file_sha256: str,
    rights_manifest: dict[str, Any],
    rights_manifest_file_sha256: str,
    source_run_id: str,
) -> dict[str, Any]:
    """Join one factory artifact with completed human and rights evidence.

    The strongest result is ``READY_FOR_PRIVATE_REVIEW``.  A separate workflow
    dispatch and explicit confirmation are still required for an upload.
    """

    failures: list[str] = []
    warnings: list[str] = []
    root = Path(artifact_root).resolve()
    if not root.is_dir():
        raise Acc1ReleaseGateError("factory artifact root must be a directory")
    if not re.fullmatch(r"[1-9][0-9]*", str(source_run_id or "")):
        failures.append("source_run_id must be a positive GitHub run id")
    release_manifest_path = root / "release-candidate-manifest.json"
    release_manifest = load_object(release_manifest_path)
    recorded_manifest_hash = str(
        release_manifest.get("release_candidate_manifest_sha256") or ""
    ).strip().lower()
    unhashed_manifest = dict(release_manifest)
    unhashed_manifest.pop("release_candidate_manifest_sha256", None)
    if not _valid_hash(recorded_manifest_hash):
        failures.append("factory release-candidate manifest self hash is invalid")
    elif recorded_manifest_hash != canonical_hash(unhashed_manifest):
        failures.append("factory release-candidate manifest self hash does not match")
    if release_manifest.get("version") != 2:
        failures.append("factory release-candidate manifest version must be 2")
    if release_manifest.get("status") != "READY_FOR_HUMAN_REVIEW":
        failures.append("factory artifact must be READY_FOR_HUMAN_REVIEW")
    if release_manifest.get("publication_authorized") is not False:
        failures.append("factory manifest publication_authorized must remain false")
    if release_manifest.get("media_qa_status") != "PASS":
        failures.append("factory manifest media_qa_status must PASS")
    if release_manifest.get("creative_review_status") != "BLOCKED_PENDING_HUMAN":
        failures.append("factory manifest must preserve the original pending-human ceiling")
    if release_manifest.get("performance_outcome_guaranteed") is not False:
        failures.append("factory manifest must not guarantee performance")
    try:
        visual_mode = resolve_visual_mode(release_manifest.get("visual_mode"))
    except ValueError:
        visual_mode = ""
        failures.append("factory manifest visual_mode is invalid")

    evidence_paths = dict(FACTORY_EVIDENCE_PATHS)
    if visual_mode == CINEMATIC_STORY_MODE:
        evidence_paths.update(FACTORY_CINEMATIC_EVIDENCE_PATHS)
    elif visual_mode == EDITORIAL_MOTION_MODE:
        evidence_paths.update(FACTORY_EDITORIAL_MOTION_EVIDENCE_PATHS)
    artifact_hashes = _verify_claimed_files(
        root=root,
        paths=FACTORY_ARTIFACT_PATHS,
        claimed=release_manifest.get("artifact_sha256"),
        label="artifact",
        failures=failures,
    )
    _verify_claimed_files(
        root=root,
        paths=evidence_paths,
        claimed=release_manifest.get("evidence_sha256"),
        label="evidence",
        failures=failures,
    )

    episode_plan = load_object(root / "episode-plan.json")
    source_queue = load_object(root / "source-queue.json")
    topic_playoff = load_object(root / "topic-playoff.json")
    greenlight = load_object(root / "episode-greenlight.json")
    plan_validation = validate_episode_manifest(
        episode_plan,
        source_queue=source_queue,
        topic_review=topic_playoff,
        greenlight=greenlight,
    )
    if plan_validation.get("status") != "PASS":
        failures.extend(
            f"episode plan: {failure}"
            for failure in plan_validation.get("failures") or []
        )
    for field in (
        "episode_key", "pilot_id", "format", "pillar", "visual_mode",
        "narration_profile_id", "narration_profile_sha256",
        "episode_plan_sha256", "daily_plan_sha256",
    ):
        if release_manifest.get(field) != episode_plan.get(field):
            failures.append(f"factory manifest {field} does not match episode plan")
    if release_manifest.get("audio_sha256") != artifact_hashes.get("audio_sha256"):
        failures.append("factory manifest audio_sha256 does not match exact audio")

    media_qa = load_object(root / "media-qa.json")
    if media_qa.get("status") != "PASS" or media_qa.get("failures"):
        failures.append("factory media QA must PASS without failures")
    if media_qa.get("publication_authorized") is not False:
        failures.append("factory media QA publication_authorized must remain false")
    if media_qa.get("episode_plan_sha256") != episode_plan.get("episode_plan_sha256"):
        failures.append("factory media QA is not bound to the episode plan")
    if media_qa.get("visual_mode") != visual_mode:
        failures.append("factory media QA visual_mode does not match")
    media_artifacts = media_qa.get("artifact_sha256")
    if not isinstance(media_artifacts, dict):
        failures.append("factory media QA artifact checksums are required")
        media_artifacts = {}
    for field, digest in artifact_hashes.items():
        if str(media_artifacts.get(field) or "").lower() != digest:
            failures.append(f"factory media QA {field} does not match exact artifact")
    for field in (
        "pause_map_sha256", "audio_mix_report_sha256", "shot_plan_sha256",
        "motion_plan_sha256",
        "caption_track_sha256", "caption_srt_sha256",
    ):
        if media_qa.get(field) != release_manifest.get(field):
            failures.append(f"factory media QA {field} binding does not match")

    thumbnail_manifest = load_object(root / "thumbnail-manifest.json")
    if thumbnail_manifest.get("status") != "PASS":
        failures.append("factory thumbnail manifest must PASS")
    if thumbnail_manifest.get("episode_plan_sha256") != episode_plan.get("episode_plan_sha256"):
        failures.append("factory thumbnail manifest is not bound to the episode plan")
    if str(thumbnail_manifest.get("sha256") or "").lower() != artifact_hashes.get("thumbnail_sha256"):
        failures.append("factory thumbnail manifest checksum does not match")

    failures.extend(_validate_factory_creative_review(
        creative_review,
        release_manifest=release_manifest,
        artifact_hashes=artifact_hashes,
    ))
    if not _valid_hash(creative_review_file_sha256):
        failures.append("completed creative review file SHA-256 is required")
    rights_report = validate_rights_manifest(
        rights_manifest,
        episode_plan=episode_plan,
        source_queue=source_queue,
        required_youtube_scope="private",
    )
    if rights_report.get("status") != "PASS":
        failures.extend(
            f"rights: {failure}" for failure in rights_report.get("failures") or []
        )
    warnings.extend(
        f"rights: {warning}" for warning in rights_report.get("warnings") or []
    )
    if not _valid_hash(rights_manifest_file_sha256):
        failures.append("rights manifest file SHA-256 is required")

    report: dict[str, Any] = {
        "version": 1,
        "status": "READY_FOR_PRIVATE_REVIEW" if not failures else "BLOCKED",
        "publication_authorized": False,
        "upload_authorized": False,
        "source_run_id": str(source_run_id),
        "release_candidate_manifest_sha256": recorded_manifest_hash or None,
        "episode_key": release_manifest.get("episode_key"),
        "episode_plan_sha256": episode_plan.get("episode_plan_sha256"),
        "visual_mode": visual_mode or None,
        "artifact_sha256": {
            field: artifact_hashes.get(field) for field in FACTORY_ARTIFACT_PATHS
        },
        "creative_review_file_sha256": creative_review_file_sha256,
        "rights_manifest_file_sha256": rights_manifest_file_sha256,
        "rights_manifest_sha256": rights_report.get("rights_manifest_sha256"),
        "required_upload_scope": "private",
        "failures": failures,
        "warnings": warnings,
        "next_gate": "separate exact private-upload workflow authorization",
    }
    report["release_gate_sha256"] = canonical_hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-report")
    parser.add_argument("--greenlight-report")
    parser.add_argument("--source-queue")
    parser.add_argument("--topic-review")
    parser.add_argument("--greenlight")
    parser.add_argument("--config")
    parser.add_argument("--episode-plan")
    parser.add_argument("--media-qa")
    parser.add_argument("--thumbnail-manifest")
    parser.add_argument("--creative-review")
    parser.add_argument("--script")
    parser.add_argument("--audio")
    parser.add_argument("--metadata")
    parser.add_argument("--storyboard")
    parser.add_argument("--video")
    parser.add_argument("--thumbnail")
    parser.add_argument("--factory-artifact-root")
    parser.add_argument("--factory-creative-review")
    parser.add_argument("--rights-manifest")
    parser.add_argument("--source-run-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    factory_mode = any((
        args.factory_artifact_root,
        args.factory_creative_review,
        args.rights_manifest,
        args.source_run_id,
    ))
    if factory_mode:
        required = {
            "--factory-artifact-root": args.factory_artifact_root,
            "--factory-creative-review": args.factory_creative_review,
            "--rights-manifest": args.rights_manifest,
            "--source-run-id": args.source_run_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise Acc1ReleaseGateError(
                "factory release arguments are missing: " + ", ".join(missing),
            )
        creative_path = Path(args.factory_creative_review)
        rights_path = Path(args.rights_manifest)
        for path in (creative_path, rights_path):
            if not path.is_file():
                raise Acc1ReleaseGateError(f"release review artifact is missing: {path}")
        report = validate_factory_release(
            artifact_root=Path(args.factory_artifact_root),
            creative_review=load_object(creative_path),
            creative_review_file_sha256=sha256_file(creative_path),
            rights_manifest=load_object(rights_path),
            rights_manifest_file_sha256=sha256_file(rights_path),
            source_run_id=args.source_run_id,
        )
        ready_status = "READY_FOR_PRIVATE_REVIEW"
    else:
        legacy_names = (
            "strategy_report", "greenlight_report", "source_queue",
            "topic_review", "greenlight", "config", "episode_plan",
            "media_qa", "thumbnail_manifest", "creative_review", "script",
            "audio", "metadata", "storyboard", "video", "thumbnail",
        )
        missing = [
            "--" + name.replace("_", "-")
            for name in legacy_names
            if not getattr(args, name)
        ]
        if missing:
            raise Acc1ReleaseGateError(
                "legacy release arguments are missing: " + ", ".join(missing),
            )
        artifact_paths = {
            "script_sha256": Path(args.script),
            "audio_sha256": Path(args.audio),
            "metadata_sha256": Path(args.metadata),
            "storyboard_sha256": Path(args.storyboard),
            "video_sha256": Path(args.video),
            "thumbnail_sha256": Path(args.thumbnail),
        }
        missing_paths = [str(path) for path in artifact_paths.values() if not path.is_file()]
        if missing_paths:
            raise Acc1ReleaseGateError(
                "release artifacts are missing: " + ", ".join(missing_paths),
            )
        report = validate_release(
            strategy_report=load_object(Path(args.strategy_report)),
            greenlight_report=load_object(Path(args.greenlight_report)),
            source_queue=load_object(Path(args.source_queue)),
            topic_review=load_object(Path(args.topic_review)),
            greenlight=load_object(Path(args.greenlight)),
            config=load_object(Path(args.config)),
            episode_plan=load_object(Path(args.episode_plan)),
            media_qa=load_object(Path(args.media_qa)),
            thumbnail_manifest=load_object(Path(args.thumbnail_manifest)),
            creative_review=load_object(Path(args.creative_review)),
            artifact_sha256={
                field: sha256_file(path) for field, path in artifact_paths.items()
            },
        )
        ready_status = "READY_FOR_UNLISTED_REVIEW"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == ready_status else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, Acc1ReleaseGateError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
