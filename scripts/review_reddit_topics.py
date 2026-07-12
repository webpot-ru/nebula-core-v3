#!/usr/bin/env python3
"""Deterministic full-body topic review for bounded Reddit candidate queues."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[a-zA-Z']+")
SERIES_RE = re.compile(r"\b(?:part|chapter|episode|season)\s*(?:one|two|three|[0-9]+)\b|\bseries\b", re.I)
OPEN_ENDING_RE = re.compile(
    r"\b(?:to be continued|i(?:'m| am) still waiting|i don'?t know what happens next|"
    r"i(?:'m| am) writing this in case|if anything happens to me|in case .{0,60} happens to me)\b",
    re.I,
)


THEMES: tuple[dict[str, Any], ...] = (
    {
        "id": "forbidden_rule_system",
        "label_ru": "Одно запретное правило в обычной системе",
        "terms": ("rule", "rules", "forbidden", "never", "do not", "don't", "must not", "exactly"),
    },
    {
        "id": "family_home_anomaly",
        "label_ru": "Семейная или домашняя аномалия",
        "terms": (
            "mother", "father", "mom", "dad", "parent", "parents", "brother", "sister",
            "family", "house", "home", "apartment", "neighbour", "neighbor", "childhood",
        ),
    },
    {
        "id": "night_work_role",
        "label_ru": "Ночная работа с невозможной обязанностью",
        "terms": (
            "night shift", "graveyard shift", "boss", "job", "work", "dispatcher", "driver",
            "sitter", "security", "janitor", "maintenance", "delivery", "mop", "call center",
        ),
    },
    {
        "id": "public_space_travel_trap",
        "label_ru": "Ловушка в дороге или общественном месте",
        "terms": (
            "subway", "train", "bus", "road", "highway", "station", "diner", "restaurant",
            "aquarium", "hotel", "elevator", "airport", "parking", "tunnel",
        ),
    },
    {
        "id": "haunted_media_record",
        "label_ru": "Запись или сообщение, которого не должно существовать",
        "terms": (
            "video", "camera", "recording", "tape", "card", "letter", "message", "text",
            "phone", "announcement", "photo", "photograph", "screen", "mail",
        ),
    },
    {
        "id": "boundary_anomaly",
        "label_ru": "Граница, которую нельзя пересекать или проверять",
        "terms": (
            "line", "boundary", "cross", "fence", "door", "peephole", "threshold", "gate",
            "bridge", "border", "entrance", "window",
        ),
    },
)


def load_queue(path: Path, allow_missing: bool) -> dict[str, Any]:
    if not path.exists():
        if allow_missing:
            return {}
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("queue must be a JSON object")
    return data


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def term_hits(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text))


def truth_mode(subreddit: str) -> str:
    normalized = subreddit.casefold().removeprefix("r/")
    if normalized == "nosleep":
        return "fiction"
    if normalized in {"letsnotmeet", "creepyencounters", "glitch_in_the_matrix", "truescarystories"}:
        return "unverified_personal_account"
    if normalized == "unresolvedmysteries":
        return "evidence_required"
    return "unknown"


def candidate_risks(entry: dict[str, Any], body: str) -> list[str]:
    risks: list[str] = []
    if entry.get("source_has_url") or entry.get("source_has_markdown_link") or entry.get("source_has_markdown_image"):
        risks.append("external_dependency")
    title = str(entry.get("title") or "")
    if SERIES_RE.search(title):
        risks.append("possible_series_dependency")
    ending = body[-1600:]
    if OPEN_ENDING_RE.search(ending):
        risks.append("possible_open_ending")
    word_count = len(WORD_RE.findall(body))
    if word_count < 2500:
        risks.append("short_source_for_target_runtime")
    mode = truth_mode(str(entry.get("subreddit") or ""))
    if mode == "unverified_personal_account":
        risks.append("unverified_claim")
    elif mode == "evidence_required":
        risks.append("factual_evidence_required")
    elif mode == "unknown":
        risks.append("truth_mode_unknown")
    return risks


def analyze_entry(entry: dict[str, Any]) -> dict[str, Any]:
    body = str(entry.get("source_body") or "")
    if not body.strip():
        raise ValueError(f"candidate {entry.get('post_id') or '(unknown)'} has no source_body")
    title = str(entry.get("title") or "")
    title_text = normalized_text(title)
    full_text = normalized_text(f"{title}\n{body}")
    theme_scores: dict[str, int] = {}
    for theme in THEMES:
        title_hits = term_hits(title_text, theme["terms"])
        full_hits = term_hits(full_text, theme["terms"])
        # The topic promise must be visible in the title. The full body is still
        # read for structure/risk evidence, but incidental words cannot assign a theme.
        score = (title_hits * 5) + min(full_hits, 3) if title_hits else 0
        if score:
            theme_scores[theme["id"]] = score

    word_count = len(WORD_RE.findall(body))
    risks = candidate_risks(entry, body)
    local_score = int(entry.get("local_score") or 0)
    length_bonus = 12 if 2500 <= word_count <= 6500 else 6 if 1400 <= word_count < 2500 else 0
    risk_penalty = 8 * len(risks)
    strongest_theme = max(theme_scores.values(), default=0)
    shortlist_score = local_score + length_bonus + (strongest_theme * 4) - risk_penalty
    return {
        "post_id": entry.get("post_id"),
        "title": title,
        "subreddit": entry.get("subreddit"),
        "source_body_chars": len(body),
        "source_word_count": word_count,
        "truth_mode": truth_mode(str(entry.get("subreddit") or "")),
        "theme_scores": theme_scores,
        "risks": risks,
        "shortlist_score": shortlist_score,
        "review_status": "SHORTLIST_FOR_RIGHTS_REVIEW",
    }


def build_review(queue: dict[str, Any], top_n: int) -> dict[str, Any]:
    raw_entries = queue.get("entries") or []
    if not raw_entries:
        return {
            "version": 1,
            "status": "no_candidates",
            "review_mode": "deterministic_full_body",
            "channel_id": queue.get("channel_id"),
            "format_intent": queue.get("format_intent"),
            "candidate_count": 0,
            "themes": [],
            "top_topics": [],
        }

    candidates = [analyze_entry(entry) for entry in raw_entries if isinstance(entry, dict)]
    theme_rows: list[dict[str, Any]] = []
    by_id = {theme["id"]: theme for theme in THEMES}
    for theme_id, theme in by_id.items():
        matches = [candidate for candidate in candidates if candidate["theme_scores"].get(theme_id)]
        if not matches:
            continue
        matches.sort(
            key=lambda candidate: (
                candidate["theme_scores"][theme_id],
                candidate["shortlist_score"],
            ),
            reverse=True,
        )
        theme_rows.append({
            "id": theme_id,
            "label_ru": theme["label_ru"],
            "candidate_count": len(matches),
            "signal_score": sum(candidate["theme_scores"][theme_id] for candidate in matches),
            "best_candidate_score": max(candidate["shortlist_score"] for candidate in matches),
            "candidate_post_ids": [candidate["post_id"] for candidate in matches],
        })
    theme_rows.sort(
        key=lambda row: (row["best_candidate_score"], row["signal_score"], row["candidate_count"]),
        reverse=True,
    )

    chosen: list[dict[str, Any]] = []
    used_posts: set[str] = set()
    remaining_themes = list(theme_rows)
    while remaining_themes and len(chosen) < top_n:
        available: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for theme in remaining_themes:
            options = [
                candidate for candidate in candidates
                if candidate["theme_scores"].get(theme["id"])
                and candidate["post_id"] not in used_posts
            ]
            if not options:
                continue
            options.sort(
                key=lambda candidate: (
                    candidate["shortlist_score"],
                    candidate["theme_scores"][theme["id"]],
                ),
                reverse=True,
            )
            available.append((theme, options[0]))
        if not available:
            break
        theme, best = max(
            available,
            key=lambda item: (
                item[1]["shortlist_score"],
                item[1]["theme_scores"][item[0]["id"]],
                item[0]["signal_score"],
            ),
        )
        candidate = dict(best)
        candidate["theme_id"] = theme["id"]
        candidate["theme_label_ru"] = theme["label_ru"]
        candidate["why_shortlisted"] = (
            "full source body matches a repeatable acc1 archetype; requires manual story and rights review"
        )
        chosen.append(candidate)
        used_posts.add(str(candidate["post_id"]))
        remaining_themes = [item for item in remaining_themes if item["id"] != theme["id"]]

    return {
        "version": 1,
        "status": "review_ready" if chosen else "no_theme_match",
        "review_mode": "deterministic_full_body",
        "channel_id": queue.get("channel_id"),
        "format_intent": queue.get("format_intent"),
        "candidate_count": len(candidates),
        "themes": theme_rows,
        "top_topics": chosen,
        "production_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    queue = load_queue(Path(args.queue), args.allow_missing)
    review = build_review(queue, max(1, args.top_n))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": review["status"],
        "candidate_count": review["candidate_count"],
        "top_topic_count": len(review["top_topics"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
