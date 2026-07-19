"""Deterministic, no-spend daily episode planner for the acc1 pilot cycle.

The planner chooses exactly one configured pilot for one Europe/Moscow
production date.  It never authorizes provider spend or publication; those
decisions remain explicit downstream gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from acc1_story_strategy import (
    EXPECTED_PILOT_CYCLE_ORDER,
    StrategyContractError,
    resolve_pilot_source_plan,
    validate_channel_strategy,
)
from acc1_visual_contract import adult_animation_profile_for_pilot


PLAN_SCHEMA_VERSION = "acc1_daily_episode_plan_v1"
MOSCOW_TIMEZONE = "Europe/Moscow"
PILOT_CYCLE_ANCHOR = date(2026, 7, 14)
MAX_RELEASE_STATUS = "READY_FOR_HUMAN_REVIEW"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DailyPlanError(ValueError):
    """Raised when a daily plan cannot be derived without guessing."""


def _read_config(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DailyPlanError(f"cannot read channels config {path}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DailyPlanError(f"channels config must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DailyPlanError("channels config must contain a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def _acc1_channel(config: dict[str, Any]) -> dict[str, Any]:
    matches = [
        item
        for item in config.get("channels") or []
        if isinstance(item, dict) and item.get("id") == "acc1"
    ]
    if len(matches) != 1:
        raise DailyPlanError("channels config must contain exactly one acc1 channel")
    return matches[0]


def resolve_production_date(
    explicit_date: str | None = None,
    *,
    now: datetime | None = None,
) -> date:
    """Resolve an explicit ISO date or today's date in Europe/Moscow."""
    if explicit_date:
        if not DATE_RE.fullmatch(explicit_date):
            raise DailyPlanError("production_date must use exact YYYY-MM-DD format")
        try:
            return date.fromisoformat(explicit_date)
        except ValueError as exc:
            raise DailyPlanError(f"production_date is not a valid date: {explicit_date}") from exc

    clock = now if now is not None else datetime.now(tz=ZoneInfo(MOSCOW_TIMEZONE))
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise DailyPlanError("automatic production_date requires a timezone-aware clock")
    return clock.astimezone(ZoneInfo(MOSCOW_TIMEZONE)).date()


def _canonical_cycle(channel: dict[str, Any]) -> tuple[str, ...]:
    cadence = channel.get("cadence_plan")
    if not isinstance(cadence, dict):
        raise DailyPlanError("acc1 cadence_plan must be an object")
    cycle = tuple(cadence.get("pilot_cycle_order") or ())
    if cycle != EXPECTED_PILOT_CYCLE_ORDER:
        raise DailyPlanError(
            "acc1 cadence_plan.pilot_cycle_order does not match the canonical pilot cycle"
        )
    return cycle


def select_daily_pilot(
    channel: dict[str, Any],
    production_date: date,
    *,
    pilot_override: str | None = None,
) -> tuple[str, int, str]:
    """Return pilot id, canonical cycle index, and selection mode."""
    cycle = _canonical_cycle(channel)
    if pilot_override is not None:
        if pilot_override not in cycle:
            raise DailyPlanError(
                "pilot override must exactly match one canonical pilot id: "
                + ", ".join(cycle)
            )
        return pilot_override, cycle.index(pilot_override), "exact_pilot_override"

    cycle_index = (production_date - PILOT_CYCLE_ANCHOR).days % len(cycle)
    return cycle[cycle_index], cycle_index, "canonical_daily_cycle"


def build_daily_plan(
    channels_path: Path | str = Path("channels.json"),
    *,
    production_date: str | None = None,
    pilot_override: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one immutable planning payload without network or provider access."""
    path = Path(channels_path)
    config, config_sha256 = _read_config(path)
    channel = _acc1_channel(config)

    strategy_report = validate_channel_strategy(channel)
    if strategy_report.get("status") != "PASS":
        failures = strategy_report.get("failures") or ["unknown strategy validation failure"]
        raise DailyPlanError("acc1 strategy is blocked: " + "; ".join(map(str, failures)))

    resolved_date = resolve_production_date(production_date, now=now)
    pilot_id, cycle_index, selection_mode = select_daily_pilot(
        channel,
        resolved_date,
        pilot_override=pilot_override,
    )
    try:
        source_plan = resolve_pilot_source_plan(channel, pilot_id)
    except StrategyContractError as exc:
        raise DailyPlanError(f"cannot resolve source plan for {pilot_id}: {exc}") from exc

    if not SHA256_RE.fullmatch(config_sha256):
        raise DailyPlanError("internal error: invalid channels config hash")

    episode_key = f"acc1/{resolved_date.isoformat()}/{pilot_id}"
    editorial_motion_style_profile = adult_animation_profile_for_pilot(pilot_id)
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "PLANNED_ARTIFACT_ONLY",
        "channel_id": "acc1",
        "production_date": resolved_date.isoformat(),
        "production_timezone": MOSCOW_TIMEZONE,
        "daily_slot": 1,
        "episodes_per_day": 1,
        "pilot_id": pilot_id,
        "format": source_plan["format"],
        "pillar": source_plan["pillar"],
        "editorial_motion_style_profile": editorial_motion_style_profile,
        "episode_key": episode_key,
        "selection": {
            "mode": selection_mode,
            "cycle_anchor_date": PILOT_CYCLE_ANCHOR.isoformat(),
            "cycle_index": cycle_index,
            "pilot_cycle_order": list(EXPECTED_PILOT_CYCLE_ORDER),
        },
        "strategy_version": config.get("strategy_version"),
        "config_sha256": config_sha256,
        "viewer_promise": channel.get("viewer_promise"),
        "source_plan": source_plan,
        "provider_spend_authorized": False,
        "publication_authorized": False,
        "max_release_status": MAX_RELEASE_STATUS,
        "performance_outcome_guaranteed": False,
    }


def _serialized_plan(plan: dict[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_plan(path: Path, plan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(_serialized_plan(plan), encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channels", default="channels.json")
    parser.add_argument("--production-date")
    parser.add_argument("--pilot-id")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        plan = build_daily_plan(
            args.channels,
            production_date=args.production_date,
            pilot_override=args.pilot_id,
        )
        if args.output:
            write_plan(Path(args.output), plan)
    except DailyPlanError as exc:
        parser.error(str(exc))
    print(_serialized_plan(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
