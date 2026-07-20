#!/usr/bin/env python3
"""Deterministically assemble fail-closed acc1 BUNDLE source manifests.

The selector is network-free and provider-free.  It accepts already reviewed
full-body candidates, rejects incomplete or ambiguous sources, and chooses
canonical subsets inside the exact pilot story-count and aggregate-runtime
envelopes.  Selection does not authorize production or publication.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import itertools
import json
import sys
from pathlib import Path
from typing import Any

from acc1_story_strategy import WORD_RE, resolve_pilot_source_plan


TRUTH_MODES = {"fiction", "unverified_personal_account"}
BUNDLE_REVIEW_STATUS = "BUNDLE_COMPONENT_ELIGIBLE"
MIN_FINALISTS = 3
MAX_FINALISTS = 10
BUNDLE_PILOT_CONTRACTS = {
    "pilot_01": {"pillar": "relationships_family", "story_count": [2, 3]},
    "pilot_02": {"pillar": "work_money_justice", "story_count": [3, 5]},
}


class BundleSelectionError(RuntimeError):
    """Raised when an exact BUNDLE source manifest cannot be assembled."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BundleSelectionError(f"candidate data is not canonical JSON: {exc}") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_body(candidate: dict[str, Any]) -> str:
    if "source_body" in candidate:
        return str(candidate.get("source_body") or "")
    return str(candidate.get("body") or "")


def _source_url(candidate: dict[str, Any]) -> str:
    return _text(candidate.get("source_url") or candidate.get("url"))


def _author_key(author: str) -> str:
    normalized = author.casefold()
    return normalized[2:] if normalized.startswith("u/") else normalized


def _url_key(url: str) -> str:
    return url.casefold().rstrip("/")


def _normalize_candidate(
    candidate: Any,
    *,
    expected_pillar: str,
    require_reviewed: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(candidate, dict):
        return None, {"candidate_ref": content_hash(candidate)[:16], "reasons": ["not_an_object"]}

    reasons: list[str] = []
    post_id = _text(candidate.get("post_id") or candidate.get("id")).casefold()
    title = _text(candidate.get("title"))
    subreddit = _text(candidate.get("subreddit"))
    author = _text(candidate.get("author"))
    source_url = _source_url(candidate)
    story_signature = _text(candidate.get("story_signature"))
    pillar_id = _text(candidate.get("pillar_id") or candidate.get("pillar"))
    truth_mode = _text(candidate.get("truth_mode"))
    review_status = _text(candidate.get("review_status"))
    body = _source_body(candidate)
    payoff_evidence = _text(candidate.get("payoff_evidence"))

    required_text = {
        "post_id": post_id,
        "title": title,
        "subreddit": subreddit,
        "author": author,
        "source_url": source_url,
        "story_signature": story_signature,
        "source_body": body.strip(),
        "payoff_evidence": payoff_evidence,
    }
    for field, value in required_text.items():
        if not value:
            reasons.append(f"missing_{field}")
    if pillar_id != expected_pillar:
        reasons.append("wrong_pillar")
    if truth_mode not in TRUTH_MODES:
        reasons.append("unsupported_truth_mode")
    if require_reviewed and review_status != BUNDLE_REVIEW_STATUS:
        reasons.append("candidate_not_bundle_review_eligible")
    if candidate.get("complete") is not True:
        reasons.append("source_not_complete")
    if candidate.get("self_contained") is not True:
        reasons.append("source_not_self_contained")
    if candidate.get("payoff_complete") is not True:
        reasons.append("payoff_not_complete")
    if candidate.get("depends_on_screenshot_or_link") is not False:
        reasons.append("external_context_dependency")
    if candidate.get("blocking_reasons"):
        reasons.append("candidate_contains_blocking_reasons")
    if body and payoff_evidence and payoff_evidence not in body:
        reasons.append("payoff_evidence_not_in_source")

    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    word_count = len(WORD_RE.findall(body))
    recorded_hash = _text(candidate.get("source_body_sha256") or candidate.get("body_sha256"))
    if recorded_hash and recorded_hash != body_sha256:
        reasons.append("source_body_hash_mismatch")
    recorded_word_count = candidate.get("source_word_count")
    if recorded_word_count is not None and recorded_word_count != word_count:
        reasons.append("source_word_count_mismatch")
    if word_count <= 0:
        reasons.append("empty_source_word_count")

    candidate_ref = post_id or content_hash(candidate)[:16]
    if reasons:
        return None, {"candidate_ref": candidate_ref, "reasons": sorted(set(reasons))}

    normalized = {
        "post_id": post_id,
        "title": title,
        "subreddit": subreddit,
        "author": author,
        "source_url": source_url,
        "story_signature": story_signature,
        "pillar_id": pillar_id,
        "truth_mode": truth_mode,
        "review_status": review_status or None,
        "source_body": body,
        "source_body_sha256": body_sha256,
        "source_word_count": word_count,
        "complete": True,
        "self_contained": True,
        "payoff_complete": True,
        "payoff_evidence": payoff_evidence,
        "depends_on_screenshot_or_link": False,
    }
    return normalized, None


def _has_unique_sources(stories: tuple[dict[str, Any], ...]) -> bool:
    keys = (
        (story["post_id"] for story in stories),
        (_url_key(story["source_url"]) for story in stories),
        (story["source_body_sha256"] for story in stories),
        (story["story_signature"].casefold() for story in stories),
        (_author_key(story["author"]) for story in stories),
    )
    for values in keys:
        materialized = list(values)
        if len(set(materialized)) != len(materialized):
            return False
    return True


def _candidate_subsets(
    candidates: list[dict[str, Any]],
    *,
    story_count: list[int],
    aggregate_word_count: list[int],
) -> list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]]:
    minimum_stories, maximum_stories = story_count
    minimum_words, maximum_words = aggregate_word_count
    target_words = (minimum_words + maximum_words) / 2
    choices: list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]] = []
    for count in range(minimum_stories, maximum_stories + 1):
        for stories in itertools.combinations(candidates, count):
            if len({story["truth_mode"] for story in stories}) != 1:
                continue
            if not _has_unique_sources(stories):
                continue
            total_words = sum(story["source_word_count"] for story in stories)
            if not minimum_words <= total_words <= maximum_words:
                continue
            source_ids = tuple(story["post_id"] for story in stories)
            ranking_key = (abs(total_words - target_words), count, source_ids)
            choices.append((ranking_key, stories, total_words))
    choices.sort(key=lambda item: item[0])
    return choices


def _bundle_contract(source_plan: dict[str, Any]) -> tuple[str, str, list[int], list[int]]:
    if source_plan.get("format") != "BUNDLE":
        raise BundleSelectionError("source_plan.format must be BUNDLE")
    pilot_id = _text(source_plan.get("pilot_id"))
    pillar_id = _text(source_plan.get("pillar"))
    story_count = source_plan.get("story_count")
    aggregate_word_count = source_plan.get("aggregate_source_word_count")
    if not pilot_id or not pillar_id:
        raise BundleSelectionError("source_plan pilot_id and pillar are required")
    canonical = BUNDLE_PILOT_CONTRACTS.get(pilot_id)
    if canonical is None:
        raise BundleSelectionError("BUNDLE source_plan is only defined for pilot_01 or pilot_02")
    if pillar_id != canonical["pillar"]:
        raise BundleSelectionError(
            f"source_plan {pilot_id} pillar must be {canonical['pillar']}"
        )
    if not (
        isinstance(story_count, list)
        and len(story_count) == 2
        and all(isinstance(value, int) and not isinstance(value, bool) for value in story_count)
        and 2 <= story_count[0] <= story_count[1] <= 5
    ):
        raise BundleSelectionError("source_plan story_count must be an integer range within 2-5")
    if story_count != canonical["story_count"]:
        raise BundleSelectionError(
            f"source_plan {pilot_id} story_count must be {canonical['story_count']}"
        )
    if aggregate_word_count != [2340, 3900]:
        raise BundleSelectionError("source_plan aggregate_source_word_count must be [2340, 3900]")
    if source_plan.get("format_intent") != "bundle":
        raise BundleSelectionError("source_plan.format_intent must be bundle")
    if source_plan.get("topic_family") != "human_drama":
        raise BundleSelectionError("source_plan.topic_family must be human_drama")
    if source_plan.get("source_mode") != "narrative_story":
        raise BundleSelectionError("source_plan.source_mode must be narrative_story")
    return pilot_id, pillar_id, story_count, aggregate_word_count


def _prepare_choices(
    candidates: list[Any],
    *,
    source_plan: dict[str, Any],
    require_reviewed: bool,
) -> tuple[
    str,
    str,
    list[int],
    list[int],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]],
]:
    pilot_id, pillar_id, story_count, aggregate_word_count = _bundle_contract(source_plan)
    if not isinstance(candidates, list):
        raise BundleSelectionError("candidates must be a list")

    eligible: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized, rejection = _normalize_candidate(
            candidate,
            expected_pillar=pillar_id,
            require_reviewed=require_reviewed,
        )
        if normalized is not None:
            eligible.append(normalized)
        if rejection is not None:
            rejections.append(rejection)
    eligible.sort(key=lambda item: (item["post_id"], item["source_body_sha256"]))
    rejections.sort(key=lambda item: (item["candidate_ref"], tuple(item["reasons"])))
    choices = _candidate_subsets(
        eligible,
        story_count=story_count,
        aggregate_word_count=aggregate_word_count,
    )
    return (
        pilot_id,
        pillar_id,
        story_count,
        aggregate_word_count,
        eligible,
        rejections,
        choices,
    )


def _source_id_set(stories: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(story["post_id"] for story in stories)


def _materially_distinct(
    stories: tuple[dict[str, Any], ...],
    selected: list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]],
) -> bool:
    """Require each alternative to add and remove at least one complete source.

    This rejects ordering-only copies and a larger bundle that merely appends a
    source to an existing finalist.  Source overlap remains possible because
    these are competing alternatives, not three simultaneously published
    episodes.
    """
    source_ids = _source_id_set(stories)
    return all(
        source_ids - _source_id_set(existing[1])
        and _source_id_set(existing[1]) - source_ids
        for existing in selected
    )


def _choose_materially_distinct(
    choices: list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]],
    count: int,
) -> list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]] | None:
    """Find the lexicographically first ranked compatible finalist set."""
    selected: list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], int]] = []

    def search(start: int) -> bool:
        if len(selected) == count:
            return True
        if len(choices) - start < count - len(selected):
            return False
        for index in range(start, len(choices)):
            choice = choices[index]
            if not _materially_distinct(choice[1], selected):
                continue
            selected.append(choice)
            if search(index + 1):
                return True
            selected.pop()
        return False

    return list(selected) if search(0) else None


def select_bundle(
    candidates: list[Any],
    *,
    source_plan: dict[str, Any],
) -> dict[str, Any]:
    """Return one canonical, hash-bound BUNDLE manifest or fail closed."""
    (
        pilot_id,
        pillar_id,
        story_count,
        aggregate_word_count,
        eligible,
        rejections,
        choices,
    ) = _prepare_choices(
        candidates,
        source_plan=source_plan,
        require_reviewed=False,
    )
    if not choices:
        raise BundleSelectionError(
            "no complete, self-contained, unique, same-truth BUNDLE fits "
            f"story_count={story_count} and aggregate_source_word_count={aggregate_word_count}; "
            f"eligible_candidates={len(eligible)} rejected_candidates={len(rejections)}"
        )

    _ranking_key, selected, total_words = choices[0]
    selected_stories = [dict(story, story_index=index) for index, story in enumerate(selected, start=1)]
    source_pool_sha256 = content_hash(eligible)
    selected_sources_sha256 = content_hash(selected_stories)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "BUNDLE_SOURCE_SELECTED_UNREVIEWED",
        "channel_id": "acc1",
        "pilot_id": pilot_id,
        "format": "BUNDLE",
        "pillar": pillar_id,
        "truth_mode": selected_stories[0]["truth_mode"],
        "story_count": len(selected_stories),
        "aggregate_source_word_count": total_words,
        "estimated_source_minutes_at_130_wpm": round(total_words / 130, 2),
        "stories": selected_stories,
        "selection_contract": {
            "algorithm": "canonical_subset_nearest_runtime_midpoint_v1",
            "story_count": list(story_count),
            "aggregate_source_word_count": list(aggregate_word_count),
            "candidate_count": len(candidates),
            "eligible_candidate_count": len(eligible),
            "valid_subset_count": len(choices),
            "rejections": rejections,
            "input_order_affects_selection": False,
        },
        "source_pool_sha256": source_pool_sha256,
        "selected_sources_sha256": selected_sources_sha256,
        "production_authorized": False,
        "publication_authorized": False,
    }
    manifest["manifest_sha256"] = content_hash(manifest)
    return manifest


def select_bundle_finalists(
    candidates: list[Any],
    *,
    source_plan: dict[str, Any],
    finalist_count: int = MIN_FINALISTS,
) -> dict[str, Any]:
    """Return hash-bound, materially distinct reviewed BUNDLE alternatives.

    The default and minimum output is three source subsets for the later topic
    playoff.  Every component must carry the deterministic review status
    ``BUNDLE_COMPONENT_ELIGIBLE``.  The function is input-order invariant and
    fails closed when the reviewed pool cannot support enough alternatives.
    """
    if (
        isinstance(finalist_count, bool)
        or not isinstance(finalist_count, int)
        or not MIN_FINALISTS <= finalist_count <= MAX_FINALISTS
    ):
        raise BundleSelectionError(
            f"finalist_count must be an integer between {MIN_FINALISTS} and {MAX_FINALISTS}"
        )
    (
        pilot_id,
        pillar_id,
        story_count,
        aggregate_word_count,
        eligible,
        rejections,
        choices,
    ) = _prepare_choices(
        candidates,
        source_plan=source_plan,
        require_reviewed=True,
    )
    selected_choices = _choose_materially_distinct(choices, finalist_count)
    if selected_choices is None:
        raise BundleSelectionError(
            f"fewer than {finalist_count} materially distinct reviewed BUNDLE subsets fit "
            f"story_count={story_count} and aggregate_source_word_count={aggregate_word_count}; "
            f"valid_subsets={len(choices)} eligible_candidates={len(eligible)} "
            f"rejected_candidates={len(rejections)}"
        )

    source_plan_sha256 = content_hash(source_plan)
    source_pool_sha256 = content_hash(eligible)
    finalists: list[dict[str, Any]] = []
    for rank, (_ranking_key, selected, total_words) in enumerate(selected_choices, start=1):
        stories = [dict(story, story_index=index) for index, story in enumerate(selected, start=1)]
        source_post_ids = sorted(story["post_id"] for story in stories)
        finalist: dict[str, Any] = {
            "finalist_id": f"{pilot_id}_bundle_source_{rank:02d}",
            "finalist_rank": rank,
            "format": "BUNDLE",
            "pilot_id": pilot_id,
            "pillar": pillar_id,
            "truth_mode": stories[0]["truth_mode"],
            "story_count": len(stories),
            "aggregate_source_word_count": total_words,
            "estimated_source_minutes_at_130_wpm": round(total_words / 130, 2),
            "source_post_ids": source_post_ids,
            "source_set_sha256": content_hash(source_post_ids),
            "stories": stories,
            "source_plan_sha256": source_plan_sha256,
            "source_pool_sha256": source_pool_sha256,
            "selected_sources_sha256": content_hash(stories),
            "production_authorized": False,
            "publication_authorized": False,
        }
        finalist["finalist_sha256"] = content_hash(finalist)
        finalists.append(finalist)

    bindings = {
        "source_plan_sha256": source_plan_sha256,
        "source_pool_sha256": source_pool_sha256,
        "finalists_sha256": content_hash(finalists),
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "BUNDLE_SOURCE_FINALISTS_READY_FOR_TOPIC_PLAYOFF",
        "channel_id": "acc1",
        "pilot_id": pilot_id,
        "format": "BUNDLE",
        "pillar": pillar_id,
        "finalist_count": len(finalists),
        "finalists": finalists,
        "selection_contract": {
            "algorithm": "canonical_ranked_materially_distinct_subsets_v1",
            "material_difference": "each_pair_adds_and_removes_at_least_one_complete_source",
            "story_count": list(story_count),
            "aggregate_source_word_count": list(aggregate_word_count),
            "candidate_count": len(candidates),
            "eligible_reviewed_candidate_count": len(eligible),
            "valid_subset_count": len(choices),
            "rejections": rejections,
            "input_order_affects_selection": False,
        },
        "artifact_bindings": bindings,
        "production_authorized": False,
        "publication_authorized": False,
    }
    manifest["manifest_sha256"] = content_hash(manifest)
    return manifest


def verify_manifest(manifest: dict[str, Any]) -> bool:
    if not isinstance(manifest, dict):
        return False
    expected = _text(manifest.get("manifest_sha256"))
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        return False
    unhashed = copy.deepcopy(manifest)
    unhashed.pop("manifest_sha256", None)
    try:
        actual = content_hash(unhashed)
    except BundleSelectionError:
        return False
    return hmac.compare_digest(expected, actual)


def _is_sha256(value: Any) -> bool:
    normalized = _text(value)
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def verify_finalists_manifest(manifest: dict[str, Any]) -> bool:
    """Verify outer and nested finalist bindings plus source uniqueness."""
    if not verify_manifest(manifest):
        return False
    try:
        if manifest.get("status") != "BUNDLE_SOURCE_FINALISTS_READY_FOR_TOPIC_PLAYOFF":
            return False
        if manifest.get("format") != "BUNDLE" or manifest.get("channel_id") != "acc1":
            return False
        if manifest.get("production_authorized") is not False:
            return False
        if manifest.get("publication_authorized") is not False:
            return False
        finalists = manifest.get("finalists")
        finalist_count = manifest.get("finalist_count")
        if not isinstance(finalists, list) or not MIN_FINALISTS <= len(finalists) <= MAX_FINALISTS:
            return False
        if finalist_count != len(finalists):
            return False
        contract = manifest.get("selection_contract")
        bindings = manifest.get("artifact_bindings")
        if not isinstance(contract, dict) or not isinstance(bindings, dict):
            return False
        story_count_range = contract.get("story_count")
        aggregate_range = contract.get("aggregate_source_word_count")
        if not (
            isinstance(story_count_range, list)
            and len(story_count_range) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in story_count_range)
        ):
            return False
        if aggregate_range != [2340, 3900]:
            return False
        for key in ("source_plan_sha256", "source_pool_sha256", "finalists_sha256"):
            if not _is_sha256(bindings.get(key)):
                return False
        if bindings["finalists_sha256"] != content_hash(finalists):
            return False

        source_sets: list[frozenset[str]] = []
        finalist_hashes: set[str] = set()
        for expected_rank, finalist in enumerate(finalists, start=1):
            if not isinstance(finalist, dict):
                return False
            if finalist.get("finalist_rank") != expected_rank:
                return False
            if finalist.get("format") != "BUNDLE":
                return False
            if finalist.get("pilot_id") != manifest.get("pilot_id"):
                return False
            if finalist.get("pillar") != manifest.get("pillar"):
                return False
            if finalist.get("production_authorized") is not False:
                return False
            if finalist.get("publication_authorized") is not False:
                return False
            if finalist.get("source_plan_sha256") != bindings["source_plan_sha256"]:
                return False
            if finalist.get("source_pool_sha256") != bindings["source_pool_sha256"]:
                return False
            stories = finalist.get("stories")
            if not isinstance(stories, list) or not stories:
                return False
            if finalist.get("story_count") != len(stories):
                return False
            if not story_count_range[0] <= len(stories) <= story_count_range[1]:
                return False
            total_words = sum(story["source_word_count"] for story in stories)
            if finalist.get("aggregate_source_word_count") != total_words:
                return False
            if not aggregate_range[0] <= total_words <= aggregate_range[1]:
                return False
            if not _has_unique_sources(tuple(stories)):
                return False
            truth_modes = {story["truth_mode"] for story in stories}
            if truth_modes != {finalist.get("truth_mode")}:
                return False
            if any(story.get("review_status") != BUNDLE_REVIEW_STATUS for story in stories):
                return False
            if finalist.get("selected_sources_sha256") != content_hash(stories):
                return False
            source_ids = _source_id_set(stories)
            if sorted(source_ids) != finalist.get("source_post_ids"):
                return False
            if finalist.get("source_set_sha256") != content_hash(sorted(source_ids)):
                return False
            if any(
                not (source_ids - existing and existing - source_ids)
                for existing in source_sets
            ):
                return False
            source_sets.append(source_ids)

            finalist_hash = finalist.get("finalist_sha256")
            if not _is_sha256(finalist_hash) or finalist_hash in finalist_hashes:
                return False
            unhashed_finalist = copy.deepcopy(finalist)
            unhashed_finalist.pop("finalist_sha256", None)
            if finalist_hash != content_hash(unhashed_finalist):
                return False
            finalist_hashes.add(finalist_hash)
    except (BundleSelectionError, KeyError, TypeError, ValueError):
        return False
    return True


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", default="channels.json")
    parser.add_argument("--pilot-id", required=True, choices=("pilot_01", "pilot_02"))
    parser.add_argument("--input", required=True, help="JSON list or object with candidates/entries")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        config = _read_json(Path(args.channels))
        channel = next(
            item for item in config.get("channels") or []
            if isinstance(item, dict) and item.get("id") == "acc1"
        )
        source_plan = resolve_pilot_source_plan(channel, args.pilot_id)
        raw = _read_json(Path(args.input))
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, dict):
            candidates = raw.get("candidates")
            if candidates is None:
                candidates = raw.get("entries")
            if candidates is None:
                candidates = raw.get("candidate_reviews")
        else:
            candidates = None
        if not isinstance(candidates, list):
            raise BundleSelectionError("input must be a list or contain candidates/entries")
        manifest = select_bundle(candidates, source_plan=source_plan)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, StopIteration, BundleSelectionError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps({
        "status": manifest["status"],
        "pilot_id": manifest["pilot_id"],
        "story_count": manifest["story_count"],
        "manifest_sha256": manifest["manifest_sha256"],
        "output": str(output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
