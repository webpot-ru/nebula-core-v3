"""Immutable, no-network episode-plan manifest for the acc1 production lane.

The manifest binds one editorial decision to the exact source queue, topic
review, greenlight, execution config, git revision and provider settings used
to produce it.  It never authorizes publication; its only purpose is to give
every downstream artifact one stable ``episode_plan_sha256`` identity.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


MANIFEST_VERSION = 2
SUPPORTED_MANIFEST_VERSIONS = frozenset({1, MANIFEST_VERSION})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
EPISODE_KEY_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{2,127}|acc1/\d{4}-\d{2}-\d{2}/[A-Za-z0-9][A-Za-z0-9._-]{2,63})$"
)
FORMATS = {"SAGA", "BUNDLE", "THREAD"}
TRUTH_MODES = {"fiction", "unverified_personal_account"}
DISCLOSURES = {
    "fiction": "Это художественная история с Reddit.",
    "unverified_personal_account": (
        "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
    ),
}
SECRET_KEY_SEGMENTS = frozenset({
    "apikey",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "password",
    "passwords",
    "passwd",
    "passphrase",
    "passphrases",
    "privatekey",
    "secret",
    "secrets",
    "token",
})
SECRET_KEY_SEQUENCES = (
    ("api", "key"),
    ("api", "keys"),
    ("private", "key"),
    ("private", "keys"),
    ("access", "tokens"),
    ("auth", "tokens"),
    ("bearer", "tokens"),
    ("id", "tokens"),
    ("oauth", "tokens"),
    ("refresh", "tokens"),
    ("session", "tokens"),
)


def _expected_visual_contracts(visual_mode: str) -> dict[str, dict[str, Any]]:
    """Return path-independent downstream expectations for one visual mode.

    These are deliberately *contracts*, not references to rendered artifacts.
    A manifest is upstream of a shot plan, subtitle track and audio-mix report,
    therefore storing their eventual hashes here would create a circular
    identity chain.
    """

    from acc1_visual_contract import (
        CINEMATIC_CAPTION_TRACK_VERSION,
        CINEMATIC_SHOT_PLAN_VERSION,
        CINEMATIC_STORY_MODE,
        CINEMATIC_STORY_SHOT_MAX_SECONDS,
        CINEMATIC_STORY_SHOT_MIN_SECONDS,
        DEFAULT_VISUAL_MODE,
        resolve_visual_mode,
    )

    resolved_mode = resolve_visual_mode(visual_mode)
    if resolved_mode == CINEMATIC_STORY_MODE:
        return {
            "shot_plan_contract": {
                "contract": "acc1_cinematic_shot_plan",
                "version": CINEMATIC_SHOT_PLAN_VERSION,
                "visual_mode": resolved_mode,
                "required": True,
                "story_shot_duration_seconds": {
                    "min": CINEMATIC_STORY_SHOT_MIN_SECONDS,
                    "max": CINEMATIC_STORY_SHOT_MAX_SECONDS,
                },
            },
            "caption_track_contract": {
                "contract": "acc1_cinematic_caption_track",
                "version": CINEMATIC_CAPTION_TRACK_VERSION,
                "visual_mode": resolved_mode,
                "required": True,
            },
        }
    if resolved_mode != DEFAULT_VISUAL_MODE:
        # ``resolve_visual_mode`` currently makes this unreachable, but leave
        # the guard explicit so a future visual mode cannot silently inherit
        # the baseline contract.
        raise EpisodeManifestError(f"unsupported visual_mode {resolved_mode!r}")
    return {
        "shot_plan_contract": {
            "contract": "acc1_cinematic_shot_plan",
            "version": CINEMATIC_SHOT_PLAN_VERSION,
            "visual_mode": resolved_mode,
            "required": False,
        },
        "caption_track_contract": {
            "contract": "acc1_cinematic_caption_track",
            "version": CINEMATIC_CAPTION_TRACK_VERSION,
            "visual_mode": resolved_mode,
            "required": False,
        },
    }


def _expected_audio_mix_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the exact no-provider voice-mix expectation for one profile."""

    from compilation_audio_mix import AUDIO_MIX_REPORT_VERSION, PAUSE_MAP_VERSION

    loudness = profile["voice_only_loudness"]
    return {
        "contract": "acc1_voice_only_audio_mix",
        "version": AUDIO_MIX_REPORT_VERSION,
        "pause_map_version": PAUSE_MAP_VERSION,
        "required": True,
        "narration_profile_id": profile["profile_id"],
        "narration_profile_sha256": profile["profile_sha256"],
        "voice_only_loudness": copy.deepcopy(loudness),
    }


def _resolve_manifest_profile(
    *,
    pillar: object,
    narration_profile_id: object = None,
) -> dict[str, Any]:
    """Resolve the sole canonical profile for an episode pillar, fail closed."""

    from acc1_narration_profiles import (
        NARRATION_PROFILE_IDS_BY_PILLAR,
        NarrationProfileError,
        resolve_narration_profile,
    )

    normalized_pillar = str(pillar or "").strip()
    selected = str(narration_profile_id or "").strip()
    if not selected:
        selected = NARRATION_PROFILE_IDS_BY_PILLAR.get(normalized_pillar, "")
    try:
        return resolve_narration_profile(selected, pillar_id=normalized_pillar)
    except NarrationProfileError as exc:
        raise EpisodeManifestError(str(exc)) from exc


def _resolve_visual_mode(value: object = None) -> str:
    from acc1_visual_contract import resolve_visual_mode

    try:
        return resolve_visual_mode(value)
    except ValueError as exc:
        raise EpisodeManifestError(str(exc)) from exc


class EpisodeManifestError(RuntimeError):
    """Raised when an immutable episode plan cannot be built safely."""


def canonical_hash(value: Any) -> str:
    """Hash canonical JSON without depending on input formatting or key order."""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EpisodeManifestError(f"{path} must contain a JSON object")
    return value


def disclosure_for_truth_mode(truth_mode: str) -> str:
    normalized = str(truth_mode or "").strip()
    if normalized not in DISCLOSURES:
        raise EpisodeManifestError(
            "truth_mode must be fiction or unverified_personal_account"
        )
    return DISCLOSURES[normalized]


def _normalized_source(source: dict[str, Any]) -> dict[str, str]:
    post_id = str(source.get("post_id") or "").strip()
    body_sha256 = str(
        source.get("body_sha256")
        or source.get("source_body_sha256")
        or ""
    ).strip().lower()
    truth_mode = str(source.get("truth_mode") or "").strip()
    if not post_id:
        raise EpisodeManifestError("source.post_id is required")
    if not SHA256_RE.fullmatch(body_sha256):
        raise EpisodeManifestError(
            f"source {post_id!r} requires a lowercase body SHA-256"
        )
    return {
        "post_id": post_id,
        "body_sha256": body_sha256,
        "truth_mode": truth_mode,
        "required_disclosure": disclosure_for_truth_mode(truth_mode),
    }


def extract_greenlight_sources(greenlight: dict[str, Any]) -> list[dict[str, str]]:
    """Extract source identities from supported exact greenlight shapes."""

    candidates: list[Any] = []
    if isinstance(greenlight.get("source"), dict):
        candidates = [greenlight["source"]]
    elif isinstance(greenlight.get("sources"), list):
        candidates = greenlight["sources"]
    elif isinstance(greenlight.get("stories"), list):
        candidates = [
            item.get("source_snapshot") if isinstance(item, dict) else None
            for item in greenlight["stories"]
        ]
    normalized: list[dict[str, str]] = []
    for source in candidates:
        if not isinstance(source, dict):
            raise EpisodeManifestError("greenlight source entries must be objects")
        normalized.append(_normalized_source(source))
    if not normalized:
        raise EpisodeManifestError("greenlight must contain at least one exact source")
    post_ids = [item["post_id"] for item in normalized]
    if len(post_ids) != len(set(post_ids)):
        raise EpisodeManifestError("greenlight source post_id values must be unique")
    return normalized


def _key_segments(key: Any) -> tuple[str, ...]:
    """Normalize snake, kebab, spaced and camel-case keys into exact segments."""

    raw = str(key)
    raw = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", raw)
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    return tuple(
        segment
        for segment in re.sub(r"[^a-z0-9]+", "_", raw.casefold()).split("_")
        if segment
    )


def _is_secret_key(key: Any) -> bool:
    segments = _key_segments(key)
    if any(segment in SECRET_KEY_SEGMENTS for segment in segments):
        return True
    return any(
        segments[index:index + len(sequence)] == sequence
        for sequence in SECRET_KEY_SEQUENCES
        for index in range(len(segments) - len(sequence) + 1)
    )


def _contains_secret_key(value: Any, path: str = "provider_settings") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _is_secret_key(key):
                return f"{path}.{key}"
            found = _contains_secret_key(child, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _contains_secret_key(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _queue_sources(source_queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = source_queue.get("entries")
    if not isinstance(entries, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        post_id = str(entry.get("post_id") or "").strip()
        if not post_id:
            continue
        if post_id in result:
            duplicates.add(post_id)
        result[post_id] = entry
    for post_id in duplicates:
        result.pop(post_id, None)
    return result


def _validate_source_queue(
    sources: list[dict[str, Any]], source_queue: dict[str, Any], failures: list[str],
) -> None:
    entries = source_queue.get("entries")
    if not isinstance(entries, list):
        failures.append("source_queue.entries must be a list")
        return
    queue_sources = _queue_sources(source_queue)
    for source in sources:
        post_id = str(source.get("post_id") or "")
        matches = [
            entry for entry in entries
            if isinstance(entry, dict) and str(entry.get("post_id") or "").strip() == post_id
        ]
        if len(matches) != 1 or post_id not in queue_sources:
            failures.append(
                f"source {post_id!r} must match exactly one source_queue entry"
            )
            continue
        entry = queue_sources[post_id]
        body = entry.get("source_body")
        if body is None:
            body = entry.get("body")
        if not isinstance(body, str) or not body:
            failures.append(f"source_queue entry {post_id!r} requires the full source body")
            continue
        actual_body_hash = sha256_text(body)
        if actual_body_hash != source.get("body_sha256"):
            failures.append(f"source body checksum mismatch for {post_id!r}")
        recorded = str(
            entry.get("source_body_sha256") or entry.get("body_sha256") or ""
        ).strip().lower()
        if recorded and recorded != actual_body_hash:
            failures.append(f"source_queue recorded body checksum mismatch for {post_id!r}")


def _manifest_without_self_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(manifest)
    value.pop("episode_plan_sha256", None)
    return value


def validate_episode_manifest(
    manifest: dict[str, Any],
    *,
    source_queue: dict[str, Any] | None = None,
    topic_review: dict[str, Any] | None = None,
    greenlight: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    daily_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate self identity and, when supplied, every exact upstream artifact."""

    failures: list[str] = []
    manifest_version = manifest.get("version")
    if manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        failures.append(
            "manifest version must be one of "
            + ", ".join(str(version) for version in sorted(SUPPORTED_MANIFEST_VERSIONS))
        )
    if manifest.get("status") != "LOCKED":
        failures.append("manifest status must be LOCKED")
    if manifest.get("channel_id") != "acc1":
        failures.append("manifest channel_id must be acc1")
    if manifest.get("publication_authorized") is not False:
        failures.append("manifest publication_authorized must be false")

    episode_key = str(manifest.get("episode_key") or "")
    if not EPISODE_KEY_RE.fullmatch(episode_key):
        failures.append(
            "episode_key must be a stable identifier or acc1/YYYY-MM-DD/pilot"
        )
    episode_date = str(manifest.get("episode_date") or "")
    try:
        if date.fromisoformat(episode_date).isoformat() != episode_date:
            raise ValueError
    except ValueError:
        failures.append("episode_date must use YYYY-MM-DD")
    if not str(manifest.get("pilot_id") or "").strip():
        failures.append("pilot_id is required")
    if str(manifest.get("format") or "") not in FORMATS:
        failures.append("format must be SAGA, BUNDLE, or THREAD")
    if not str(manifest.get("pillar") or "").strip():
        failures.append("pillar is required")
    if not GIT_SHA_RE.fullmatch(str(manifest.get("git_sha") or "")):
        failures.append("git_sha must be a lowercase 7-64 character hex revision")
    if episode_key.startswith("acc1/"):
        key_parts = episode_key.split("/")
        if len(key_parts) != 3:
            failures.append("canonical episode_key must contain acc1/date/pilot")
        else:
            if key_parts[1] != episode_date:
                failures.append("episode_key date does not match episode_date")
            if key_parts[2] != str(manifest.get("pilot_id") or ""):
                failures.append("episode_key pilot does not match pilot_id")

    daily_plan_sha256 = str(manifest.get("daily_plan_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(daily_plan_sha256):
        failures.append("daily_plan_sha256 must be a SHA-256 digest")
    if daily_plan is not None:
        if daily_plan_sha256 != canonical_hash(daily_plan):
            failures.append("daily_plan_sha256 does not match the exact daily plan")
        daily_fields = {
            "episode_key": "episode_key",
            "production_date": "episode_date",
            "pilot_id": "pilot_id",
            "format": "format",
            "pillar": "pillar",
        }
        for daily_field, manifest_field in daily_fields.items():
            daily_value = str(daily_plan.get(daily_field) or "")
            manifest_value = str(manifest.get(manifest_field) or "")
            if daily_field == "format":
                daily_value = daily_value.upper()
            if daily_value != manifest_value:
                failures.append(
                    f"manifest {manifest_field} does not match exact daily plan"
                )
        if daily_plan.get("publication_authorized") is not False:
            failures.append("exact daily plan publication_authorized must be false")

    providers = manifest.get("provider_settings")
    if not isinstance(providers, dict) or not providers:
        failures.append("provider_settings must be a non-empty object")
    else:
        secret_path = _contains_secret_key(providers)
        if secret_path:
            failures.append(f"provider_settings must not contain secrets: {secret_path}")

    sources = manifest.get("sources")
    normalized_sources: list[dict[str, str]] = []
    if not isinstance(sources, list) or not sources:
        failures.append("manifest sources must contain at least one source")
    else:
        try:
            normalized_sources = [_normalized_source(item) for item in sources]
        except (EpisodeManifestError, AttributeError) as exc:
            failures.append(str(exc))
        else:
            if normalized_sources != sources:
                failures.append("manifest sources must use the canonical source schema")
            post_ids = [item["post_id"] for item in normalized_sources]
            if len(post_ids) != len(set(post_ids)):
                failures.append("manifest source post_id values must be unique")

    truth_modes = {item["truth_mode"] for item in normalized_sources}
    if len(truth_modes) != 1:
        failures.append("all exact episode sources must use one truth_mode")
    episode_truth_mode = next(iter(truth_modes), "")
    episode_disclosure = DISCLOSURES.get(episode_truth_mode, "")

    disclosure_contract = manifest.get("truth_disclosure_contract")
    expected_disclosure_contract = {
        "audible_once_per_episode": True,
        "metadata_visible_once_per_episode": True,
        "truth_mode": episode_truth_mode,
        "text": episode_disclosure,
    }
    if disclosure_contract != expected_disclosure_contract:
        failures.append(
            "truth_disclosure_contract must bind one audible and metadata disclosure per episode"
        )

    # v1 manifests are historical immutable records.  Do not enrich, normalize
    # or recompute their content beyond their original self-hash validation.
    # v2 additionally binds the deterministic visual/narration contracts that
    # downstream plans must satisfy.
    if manifest_version == MANIFEST_VERSION:
        try:
            visual_mode = _resolve_visual_mode(manifest.get("visual_mode"))
        except EpisodeManifestError as exc:
            failures.append(str(exc))
            visual_mode = ""
        else:
            if manifest.get("visual_mode") != visual_mode:
                failures.append("visual_mode must be explicitly declared in v2")
        try:
            profile = _resolve_manifest_profile(
                pillar=manifest.get("pillar"),
                narration_profile_id=manifest.get("narration_profile_id"),
            )
        except EpisodeManifestError as exc:
            failures.append(str(exc))
            profile = None
        if profile is not None:
            if manifest.get("narration_profile_id") != profile["profile_id"]:
                failures.append(
                    "narration_profile_id must be explicitly declared in v2"
                )
            if manifest.get("narration_profile_sha256") != profile["profile_sha256"]:
                failures.append(
                    "narration_profile_sha256 does not match the canonical profile"
                )
            if visual_mode:
                expected_contracts = _expected_visual_contracts(visual_mode)
                for field, expected in expected_contracts.items():
                    if manifest.get(field) != expected:
                        failures.append(f"{field} does not match the visual-mode contract")
                expected_audio_contract = _expected_audio_mix_contract(profile)
                if manifest.get("audio_mix_contract") != expected_audio_contract:
                    failures.append(
                        "audio_mix_contract does not match the narration-profile contract"
                    )

    bindings = manifest.get("artifact_bindings")
    if not isinstance(bindings, dict):
        failures.append("artifact_bindings must be an object")
        bindings = {}
    exact_artifacts = {
        "queue_sha256": source_queue,
        "review_sha256": topic_review,
        "greenlight_sha256": greenlight,
        "config_sha256": config,
    }
    for field, artifact in exact_artifacts.items():
        recorded = str(bindings.get(field) or "").strip().lower()
        if not SHA256_RE.fullmatch(recorded):
            failures.append(f"artifact_bindings.{field} must be a SHA-256 digest")
        if artifact is not None and recorded != canonical_hash(artifact):
            failures.append(f"artifact_bindings.{field} does not match the exact artifact")

    if source_queue is not None and normalized_sources:
        _validate_source_queue(normalized_sources, source_queue, failures)
    if greenlight is not None:
        try:
            greenlight_sources = extract_greenlight_sources(greenlight)
        except EpisodeManifestError as exc:
            failures.append(str(exc))
        else:
            if greenlight_sources != normalized_sources:
                failures.append("manifest sources do not match exact greenlight sources")
        for field in ("pilot_id", "pillar"):
            if str(greenlight.get(field) or "") != str(manifest.get(field) or ""):
                failures.append(f"manifest {field} does not match exact greenlight")
        if str(greenlight.get("format") or "").upper() != str(manifest.get("format") or ""):
            failures.append("manifest format does not match exact greenlight")
        if greenlight.get("publication_authorized") is not False:
            failures.append("exact greenlight publication_authorized must be false")

    expected_plan_hash = canonical_hash(_manifest_without_self_hash(manifest))
    recorded_plan_hash = str(manifest.get("episode_plan_sha256") or "").strip().lower()
    if not SHA256_RE.fullmatch(recorded_plan_hash):
        failures.append("episode_plan_sha256 must be a SHA-256 digest")
    elif recorded_plan_hash != expected_plan_hash:
        failures.append("episode_plan_sha256 does not match manifest content")

    return {
        "version": manifest_version,
        "status": "PASS" if not failures else "BLOCKED",
        "publication_authorized": False,
        "episode_plan_sha256": recorded_plan_hash or None,
        "failures": failures,
    }


def build_episode_manifest(
    *,
    episode_key: str,
    episode_date: str,
    pilot_id: str,
    format_id: str,
    pillar: str,
    source_queue: dict[str, Any],
    topic_review: dict[str, Any],
    greenlight: dict[str, Any],
    config: dict[str, Any],
    daily_plan: dict[str, Any],
    git_sha: str,
    provider_settings: dict[str, Any],
    sources: list[dict[str, Any]] | None = None,
    visual_mode: str | None = None,
    narration_profile_id: str | None = None,
) -> dict[str, Any]:
    """Build and immediately validate an immutable acc1 episode plan."""

    normalized_sources = [
        _normalized_source(item)
        for item in (sources if sources is not None else extract_greenlight_sources(greenlight))
    ]
    normalized_pillar = str(pillar or "").strip()
    resolved_visual_mode = _resolve_visual_mode(visual_mode)
    narration_profile = _resolve_manifest_profile(
        pillar=normalized_pillar,
        narration_profile_id=narration_profile_id,
    )
    visual_contracts = _expected_visual_contracts(resolved_visual_mode)
    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "status": "LOCKED",
        "channel_id": "acc1",
        "episode_key": str(episode_key or "").strip(),
        "episode_date": str(episode_date or "").strip(),
        "pilot_id": str(pilot_id or "").strip(),
        "format": str(format_id or "").strip().upper(),
        "pillar": normalized_pillar,
        "daily_plan_sha256": canonical_hash(daily_plan),
        "sources": normalized_sources,
        "truth_disclosure_contract": {
            "audible_once_per_episode": True,
            "metadata_visible_once_per_episode": True,
            "truth_mode": normalized_sources[0]["truth_mode"] if normalized_sources else "",
            "text": normalized_sources[0]["required_disclosure"] if normalized_sources else "",
        },
        "artifact_bindings": {
            "queue_sha256": canonical_hash(source_queue),
            "review_sha256": canonical_hash(topic_review),
            "greenlight_sha256": canonical_hash(greenlight),
            "config_sha256": canonical_hash(config),
        },
        "git_sha": str(git_sha or "").strip().lower(),
        "provider_settings": copy.deepcopy(provider_settings),
        "visual_mode": resolved_visual_mode,
        "narration_profile_id": narration_profile["profile_id"],
        "narration_profile_sha256": narration_profile["profile_sha256"],
        **visual_contracts,
        "audio_mix_contract": _expected_audio_mix_contract(narration_profile),
        "publication_authorized": False,
    }
    manifest["episode_plan_sha256"] = canonical_hash(manifest)
    report = validate_episode_manifest(
        manifest,
        source_queue=source_queue,
        topic_review=topic_review,
        greenlight=greenlight,
        config=config,
        daily_plan=daily_plan,
    )
    if report["status"] != "PASS":
        raise EpisodeManifestError("; ".join(report["failures"]))
    return manifest


def bind_episode_plan(payload: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy stamped with both immutable episode and daily plan identities."""

    validation = validate_episode_manifest(manifest)
    if validation["status"] != "PASS":
        raise EpisodeManifestError("; ".join(validation["failures"]))
    bound = copy.deepcopy(payload)
    bound["episode_plan_sha256"] = manifest["episode_plan_sha256"]
    bound["daily_plan_sha256"] = manifest["daily_plan_sha256"]
    return bound


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-key", required=True)
    parser.add_argument("--episode-date", required=True)
    parser.add_argument("--pilot-id", required=True)
    parser.add_argument("--format", required=True, dest="format_id")
    parser.add_argument("--pillar", required=True)
    parser.add_argument("--source-queue", required=True)
    parser.add_argument("--topic-review", required=True)
    parser.add_argument("--greenlight", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--daily-plan", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--provider-settings", required=True)
    parser.add_argument("--visual-mode")
    parser.add_argument("--narration-profile-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = build_episode_manifest(
        episode_key=args.episode_key,
        episode_date=args.episode_date,
        pilot_id=args.pilot_id,
        format_id=args.format_id,
        pillar=args.pillar,
        source_queue=load_object(Path(args.source_queue)),
        topic_review=load_object(Path(args.topic_review)),
        greenlight=load_object(Path(args.greenlight)),
        config=load_object(Path(args.config)),
        daily_plan=load_object(Path(args.daily_plan)),
        git_sha=args.git_sha,
        provider_settings=load_object(Path(args.provider_settings)),
        visual_mode=args.visual_mode,
        narration_profile_id=args.narration_profile_id,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "status": "LOCKED",
        "episode_key": manifest["episode_key"],
        "episode_plan_sha256": manifest["episode_plan_sha256"],
        "publication_authorized": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, EpisodeManifestError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
