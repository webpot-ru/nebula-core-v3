import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from acc1_daily_planner import (
    DailyPlanError,
    MAX_RELEASE_STATUS,
    build_daily_plan,
    resolve_production_date,
)
from acc1_story_strategy import EXPECTED_PILOT_CYCLE_ORDER


ROOT = Path(__file__).resolve().parents[1]


class Acc1DailyPlannerTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))

    def _write_config(self, directory: str, config=None) -> Path:
        path = Path(directory) / "channels.json"
        payload = self.config if config is None else config
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def test_explicit_dates_follow_one_canonical_pilot_per_day(self):
        with tempfile.TemporaryDirectory() as directory:
            channels_path = self._write_config(directory)
            for offset, pilot_id in enumerate(EXPECTED_PILOT_CYCLE_ORDER):
                plan = build_daily_plan(
                    channels_path,
                    production_date=f"2026-07-{14 + offset:02d}",
                )
                self.assertEqual(plan["pilot_id"], pilot_id)
                self.assertEqual(plan["daily_slot"], 1)
                self.assertEqual(plan["episodes_per_day"], 1)
                self.assertEqual(
                    plan["episode_key"],
                    f"acc1/2026-07-{14 + offset:02d}/{pilot_id}",
                )

    def test_automatic_date_uses_europe_moscow_calendar_day(self):
        utc_clock = datetime(2026, 7, 13, 21, 30, tzinfo=timezone.utc)
        self.assertEqual(resolve_production_date(now=utc_clock).isoformat(), "2026-07-14")

    def test_exact_override_changes_only_the_selected_pilot(self):
        with tempfile.TemporaryDirectory() as directory:
            channels_path = self._write_config(directory)
            plan = build_daily_plan(
                channels_path,
                production_date="2026-07-14",
                pilot_override="pilot_05",
            )
            self.assertEqual(plan["pilot_id"], "pilot_05")
            self.assertEqual(plan["format"], "THREAD")
            self.assertEqual(plan["pillar"], "professions_human_experience")
            self.assertEqual(plan["selection"]["mode"], "exact_pilot_override")
            self.assertEqual(plan["selection"]["cycle_index"], 3)
            self.assertEqual(plan["source_plan"]["pillar"], "professions_human_experience")
            self.assertEqual(plan["episode_key"], "acc1/2026-07-14/pilot_05")

    def test_override_is_exact_and_invalid_dates_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            channels_path = self._write_config(directory)
            with self.assertRaises(DailyPlanError):
                build_daily_plan(
                    channels_path,
                    production_date="2026-07-14",
                    pilot_override="pilot_05 ",
                )
            with self.assertRaises(DailyPlanError):
                build_daily_plan(channels_path, production_date="2026-7-14")
            with self.assertRaises(DailyPlanError):
                build_daily_plan(channels_path, production_date="2026-02-30")

    def test_noncanonical_config_cycle_fails_closed(self):
        config = copy.deepcopy(self.config)
        channel = next(item for item in config["channels"] if item["id"] == "acc1")
        channel["cadence_plan"]["pilot_cycle_order"] = list(reversed(EXPECTED_PILOT_CYCLE_ORDER))
        with tempfile.TemporaryDirectory() as directory:
            channels_path = self._write_config(directory, config)
            with self.assertRaisesRegex(DailyPlanError, "strategy is blocked"):
                build_daily_plan(channels_path, production_date="2026-07-14")

    def test_plan_is_deterministic_hash_bound_and_never_authorizes_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            channels_path = self._write_config(directory)
            first = build_daily_plan(channels_path, production_date="2026-07-14")
            second = build_daily_plan(channels_path, production_date="2026-07-14")

            self.assertEqual(first, second)
            self.assertEqual(
                first["config_sha256"],
                hashlib.sha256(channels_path.read_bytes()).hexdigest(),
            )
            self.assertFalse(first["provider_spend_authorized"])
            self.assertFalse(first["publication_authorized"])
            self.assertFalse(first["performance_outcome_guaranteed"])
            self.assertEqual(first["max_release_status"], MAX_RELEASE_STATUS)
            self.assertEqual(first["format"], first["source_plan"]["format"])
            self.assertEqual(first["pillar"], first["source_plan"]["pillar"])
            self.assertEqual(first["editorial_motion_style_profile"], "adult_animation_family_v1")
            self.assertNotIn("topic_mix", json.dumps(first, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
