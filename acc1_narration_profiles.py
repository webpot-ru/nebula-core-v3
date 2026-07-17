"""Canonical no-voice-ID narration profiles for the five acc1 pillars."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


PROFILE_CONTRACT_VERSION = 1
VOICE_ONLY_TARGET_LUFS = -16.0
VOICE_ONLY_TOLERANCE_LU = 1.0
VOICE_ONLY_MAX_TRUE_PEAK_DBTP = -1.5

RELATIONSHIPS_FAMILY_PROFILE_ID = "acc1_relationships_family_v1"
WORK_MONEY_JUSTICE_PROFILE_ID = "acc1_work_money_justice_v1"
CONFESSIONS_AWKWARD_TABOO_PROFILE_ID = "acc1_confessions_awkward_taboo_v1"
PROFESSIONS_HUMAN_EXPERIENCE_PROFILE_ID = "acc1_professions_human_experience_v1"
STRANGE_DARK_UNEXPLAINED_PROFILE_ID = "acc1_strange_dark_unexplained_v1"

NARRATION_PROFILE_IDS_BY_PILLAR = {
    "relationships_family": RELATIONSHIPS_FAMILY_PROFILE_ID,
    "work_money_justice": WORK_MONEY_JUSTICE_PROFILE_ID,
    "confessions_awkward_taboo": CONFESSIONS_AWKWARD_TABOO_PROFILE_ID,
    "professions_human_experience": PROFESSIONS_HUMAN_EXPERIENCE_PROFILE_ID,
    "strange_dark_unexplained": STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
}
NARRATION_PROFILE_IDS = frozenset(NARRATION_PROFILE_IDS_BY_PILLAR.values())
PILLAR_IDS = frozenset(NARRATION_PROFILE_IDS_BY_PILLAR)


class NarrationProfileError(ValueError):
    """An unknown or cross-pillar narration-profile selection."""


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonicalize_voice_settings_json(value: str | dict[str, Any]) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise NarrationProfileError("voice settings must be valid JSON") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise NarrationProfileError("voice settings must be a JSON object")
    return json.dumps(
        parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def _profile(
    *,
    profile_id: str,
    pillar_id: str,
    speed: float,
    stability: float,
    style: float,
    max_chars: int,
    intra_beat_seconds: float,
    beat_seconds: float,
    segment_seconds: dict[str, float],
) -> dict[str, Any]:
    return {
        "version": PROFILE_CONTRACT_VERSION,
        "profile_id": profile_id,
        "pillar_id": pillar_id,
        "speed": speed,
        "voice_settings_json": canonicalize_voice_settings_json({
            "similarity_boost": 0.75,
            "stability": stability,
            "style": style,
            "use_speaker_boost": True,
        }),
        "semantic_chunk_policy": {
            "version": 1,
            "max_chars": max_chars,
            "boundary_order": [
                "explicit_story_beat",
                "paragraph",
                "sentence",
                "word",
            ],
            "never_cross_logical_segments": True,
            "preserve_sanitized_text": True,
        },
        "pause_after": {
            "version": 1,
            "intra_beat_seconds": intra_beat_seconds,
            "beat_seconds": beat_seconds,
            "segment_seconds": dict(segment_seconds),
        },
        "voice_only_loudness": {
            "integrated_lufs": VOICE_ONLY_TARGET_LUFS,
            "tolerance_lu": VOICE_ONLY_TOLERANCE_LU,
            "max_true_peak_dbtp": VOICE_ONLY_MAX_TRUE_PEAK_DBTP,
        },
    }


_PROFILE_PAYLOADS = {
    RELATIONSHIPS_FAMILY_PROFILE_ID: _profile(
        profile_id=RELATIONSHIPS_FAMILY_PROFILE_ID,
        pillar_id="relationships_family",
        speed=0.98,
        stability=0.48,
        style=0.08,
        max_chars=1_900,
        intra_beat_seconds=0.14,
        beat_seconds=0.48,
        segment_seconds={
            "intro": 0.65, "story": 0.72, "transition": 1.05, "outro": 0.0,
        },
    ),
    WORK_MONEY_JUSTICE_PROFILE_ID: _profile(
        profile_id=WORK_MONEY_JUSTICE_PROFILE_ID,
        pillar_id="work_money_justice",
        speed=1.02,
        stability=0.58,
        style=0.04,
        max_chars=2_100,
        intra_beat_seconds=0.11,
        beat_seconds=0.38,
        segment_seconds={
            "intro": 0.55, "story": 0.60, "transition": 0.90, "outro": 0.0,
        },
    ),
    CONFESSIONS_AWKWARD_TABOO_PROFILE_ID: _profile(
        profile_id=CONFESSIONS_AWKWARD_TABOO_PROFILE_ID,
        pillar_id="confessions_awkward_taboo",
        speed=0.96,
        stability=0.42,
        style=0.12,
        max_chars=1_750,
        intra_beat_seconds=0.16,
        beat_seconds=0.56,
        segment_seconds={
            "intro": 0.70, "story": 0.78, "transition": 1.00, "outro": 0.0,
        },
    ),
    PROFESSIONS_HUMAN_EXPERIENCE_PROFILE_ID: _profile(
        profile_id=PROFESSIONS_HUMAN_EXPERIENCE_PROFILE_ID,
        pillar_id="professions_human_experience",
        speed=0.98,
        stability=0.55,
        style=0.03,
        max_chars=2_000,
        intra_beat_seconds=0.13,
        beat_seconds=0.50,
        segment_seconds={
            "intro": 0.62, "story": 0.68, "transition": 0.95, "outro": 0.0,
        },
    ),
    STRANGE_DARK_UNEXPLAINED_PROFILE_ID: _profile(
        profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        pillar_id="strange_dark_unexplained",
        speed=0.92,
        stability=0.62,
        style=0.05,
        max_chars=1_650,
        intra_beat_seconds=0.20,
        beat_seconds=0.76,
        segment_seconds={
            "intro": 0.85, "story": 0.96, "transition": 1.30, "outro": 0.0,
        },
    ),
}

NARRATION_PROFILES: dict[str, dict[str, Any]] = {}
for _profile_id, _payload in _PROFILE_PAYLOADS.items():
    _record = copy.deepcopy(_payload)
    _record["profile_sha256"] = canonical_hash(_payload)
    NARRATION_PROFILES[_profile_id] = _record

NARRATION_PROFILE_SHA256_BY_ID = {
    profile_id: profile["profile_sha256"]
    for profile_id, profile in NARRATION_PROFILES.items()
}
NARRATION_PROFILES_SHA256 = canonical_hash([
    {
        "profile_id": profile_id,
        "profile_sha256": NARRATION_PROFILES[profile_id]["profile_sha256"],
    }
    for profile_id in sorted(NARRATION_PROFILES)
])


def profile_payload(profile: dict[str, Any]) -> dict[str, Any]:
    """Return the exact hashable profile payload without its recorded digest."""

    return {
        key: copy.deepcopy(value)
        for key, value in profile.items()
        if key != "profile_sha256"
    }


def verify_narration_profile(profile: dict[str, Any]) -> bool:
    digest = str(profile.get("profile_sha256") or "")
    return len(digest) == 64 and digest == canonical_hash(profile_payload(profile))


def resolve_narration_profile(
    profile_id: object,
    *,
    pillar_id: object,
) -> dict[str, Any]:
    """Resolve one canonical profile and reject unknown/cross-pillar selection."""

    normalized_pillar = str(pillar_id or "").strip()
    if normalized_pillar not in PILLAR_IDS:
        raise NarrationProfileError(
            "pillar must be one of " + ", ".join(sorted(PILLAR_IDS))
        )
    normalized_profile = str(profile_id or "").strip()
    profile = NARRATION_PROFILES.get(normalized_profile)
    if profile is None:
        raise NarrationProfileError(
            "narration_profile_id must be one of "
            + ", ".join(sorted(NARRATION_PROFILE_IDS))
        )
    expected_profile = NARRATION_PROFILE_IDS_BY_PILLAR[normalized_pillar]
    if normalized_profile != expected_profile:
        raise NarrationProfileError(
            f"narration profile {normalized_profile!r} does not match pillar "
            f"{normalized_pillar!r}; expected {expected_profile!r}"
        )
    if not verify_narration_profile(profile):
        raise NarrationProfileError(
            f"narration profile {normalized_profile!r} checksum is invalid"
        )
    return copy.deepcopy(profile)


get_narration_profile = resolve_narration_profile
