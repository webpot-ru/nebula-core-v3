import copy
import hashlib
import unittest

from acc1_topic_playoff import canonical_hash, run_playoff


SCORES = {
    "hook_specificity": 14,
    "stakes_clarity": 9,
    "escalation": 9,
    "payoff": 14,
    "novelty": 9,
    "russian_fit": 9,
    "discussion_potential": 9,
    "renderability": 5,
    "packaging_honesty": 10,
    "source_truth": 5,
}


def source(source_id: str, body_words: int = 2500) -> dict:
    opening = f"{source_id} opening witness noticed the locked basement door"
    middle = f"{source_id} middle revealed the warning had a different meaning"
    payoff = f"{source_id} payoff finally explained why the warning mattered"
    fixed_words = len((opening + " " + middle + " " + payoff).split())
    filler_count = max(0, body_words - fixed_words)
    first_half = filler_count // 2
    body = " ".join(
        [opening, *("word" for _ in range(first_half)), middle,
         *("word" for _ in range(filler_count - first_half)), payoff]
    )
    return {
        "source_id": source_id,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "source_url": f"https://www.reddit.com/r/test/comments/{source_id}/topic/",
        "author": f"author_{source_id}",
        "story_signature": f"signature_{source_id}",
        "truth_mode": "unverified_personal_account",
        "role": "story",
        "pillar": "strange_dark_unexplained",
        "complete": True,
        "payoff_complete": True,
        "depends_on_screenshot_or_link": False,
        "fictional_as_real": False,
    }


def candidate(candidate_id: str, score_delta: int = 0) -> dict:
    item_source = source(candidate_id)
    scores = dict(SCORES)
    scores["hook_specificity"] += score_delta
    return {
        "candidate_id": candidate_id,
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "viewer_promise_fit": True,
        "pillar_evidence": {
            "source_id": candidate_id,
            "source_quote": f"{candidate_id} opening witness noticed the locked basement door",
        },
        "sources": [item_source],
        "cold_open": {
            "text": "Свидетель заметил дверь, которая всё время оставалась запертой.",
            "source_id": candidate_id,
            "source_quote": f"{candidate_id} opening witness noticed the locked basement door",
        },
        "payoff_evidence": {
            "source_id": candidate_id,
            "source_quote": f"{candidate_id} payoff finally explained why the warning mattered",
        },
        "story_beats": [
            {
                "beat": "Завязка с конкретной угрозой",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} opening witness noticed the locked basement door",
            },
            {
                "beat": "Поворот, меняющий смысл истории",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} middle revealed the warning had a different meaning",
            },
            {
                "beat": "Развязка с полным payoff",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} payoff finally explained why the warning mattered",
            },
        ],
        "originality_plan": {
            "editorial_frame": {
                "direction": "Собрать историю вокруг смены доверия к рассказчику",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} middle revealed the warning had a different meaning",
            },
            "visual_direction": {
                "direction": "Менять визуальный акцент в момент раскрытия",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} middle revealed the warning had a different meaning",
            },
            "sound_direction": {
                "direction": "Убрать фон перед финальной фразой",
                "source_id": candidate_id,
                "source_quote": f"{candidate_id} payoff finally explained why the warning mattered",
            },
        },
        "packaging_options": [
            {
                "youtube_title": f"История {candidate_id} — угол {index}",
                "thumbnail_text": f"УГОЛ {index}",
                "first_screen_promise": f"Обещание {index}",
                "angle": f"angle-{index}",
                "source_id": candidate_id,
                "source_backing": f"{candidate_id} opening witness noticed the locked basement door",
            }
            for index in range(3)
        ],
        "veto_flags": [],
        "reviews": [
            {
                "role": role,
                "verdict": "PASS",
                "veto_flags": [],
                "scorecard": scores,
                "decision_reason": "Источник полный, обещание честное.",
            }
            for role in ("producer", "critic")
        ],
    }


def payload() -> dict:
    plan = {
        "channel_id": "acc1",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "publication_authorized": False,
    }
    return {
        "daily_plan": plan,
        "daily_plan_sha256": canonical_hash(plan),
        "candidates": [candidate("aaa"), candidate("bbb", 1), candidate("ccc")],
    }


class TopicPlayoffTests(unittest.TestCase):
    def test_selects_highest_fully_passing_candidate(self):
        result = run_playoff(payload())
        self.assertEqual(result["status"], "READY_FOR_SCRIPTING")
        self.assertEqual(result["winner"]["candidate_id"], "bbb")
        self.assertRegex(result["winner"]["creative_plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            result["winner"]["candidate_contract_sha256"],
            canonical_hash(payload()["candidates"][1]),
        )
        self.assertEqual(
            result["winner"]["packaging_options_sha256"],
            canonical_hash(payload()["candidates"][1]["packaging_options"]),
        )
        self.assertEqual(result["winner"]["story_beat_count"], 3)
        self.assertFalse(result["publication_authorized"])
        self.assertFalse(result["millions_of_views_guaranteed"])

    def test_tie_break_is_deterministic(self):
        value = payload()
        value["candidates"] = list(reversed([candidate("aaa"), candidate("bbb"), candidate("ccc")]))
        result = run_playoff(value)
        self.assertEqual(result["winner"]["candidate_id"], "aaa")

    def test_plan_hash_mismatch_blocks(self):
        value = payload()
        value["daily_plan"]["pillar"] = "relationships_family"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("daily_plan_sha256 does not match daily_plan", result["failures"])

    def test_hard_source_dependency_blocks_even_with_high_scores(self):
        value = payload()
        value["candidates"][0]["sources"][0]["depends_on_screenshot_or_link"] = True
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("screenshot" in item for item in result["candidate_reviews"][0]["failures"]))

    def test_veto_flags_require_list_schema_and_any_declared_risk_blocks(self):
        value = payload()
        value["candidates"][0]["veto_flags"] = "fictional_as_real"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "candidates[0].veto_flags must be a list",
            result["candidate_reviews"][0]["failures"],
        )

        value = payload()
        value["candidates"][0]["reviews"][1]["veto_flags"] = ["privacy_risk"]
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any(
                "privacy_risk" in failure
                for failure in result["candidate_reviews"][0]["failures"]
            )
        )

    def test_fewer_than_three_passing_finalists_blocks(self):
        value = payload()
        value["candidates"][0]["reviews"][0]["scorecard"]["source_truth"] = 0
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("at least 3 finalists must independently PASS", result["failures"])

    def test_five_candidate_reserve_survives_two_honest_review_blocks(self):
        value = payload()
        value["candidates"].extend([candidate("ddd"), candidate("eee")])
        value["candidates"][0]["reviews"][0]["scorecard"]["source_truth"] = 0
        value["candidates"][1]["reviews"][1]["scorecard"]["source_truth"] = 0
        result = run_playoff(value)
        self.assertEqual(result["status"], "READY_FOR_SCRIPTING")
        self.assertEqual(
            len([item for item in result["candidate_reviews"] if item["status"] == "PASS"]),
            3,
        )
        self.assertIn(result["winner"]["candidate_id"], {"ccc", "ddd", "eee"})

    def test_cold_open_spoken_length_is_bounded_for_one_chunk_intro(self):
        value = payload()
        value["candidates"][0]["cold_open"]["text"] = " ".join(
            ["99999999999999999999"] * 30
        )
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any(
                "500-character spoken limit" in failure
                for failure in result["candidate_reviews"][0]["failures"]
            )
        )

    def test_packaging_must_be_source_backed_and_distinct(self):
        value = payload()
        value["candidates"][0]["packaging_options"][0]["source_backing"] = "invented"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(
            any(
                "packaging_options[0].evidence" in item
                for item in result["candidate_reviews"][0]["failures"]
            )
        )

    def test_generic_evidence_and_unsubstantiated_short_cold_open_block(self):
        value = payload()
        value["candidates"][0]["pillar_evidence"]["source_quote"] = "word"
        value["candidates"][0]["cold_open"]["text"] = (
            "Президент признался в преступлении"
        )
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        failures = result["candidate_reviews"][0]["failures"]
        self.assertTrue(any("too generic" in item for item in failures))
        self.assertIn(
            "candidates[0].cold_open.text must contain 8-30 words",
            failures,
        )

    def test_body_hash_tampering_blocks(self):
        value = payload()
        value["candidates"][0]["sources"][0]["body"] += " changed"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("body_sha256" in item for item in result["candidate_reviews"][0]["failures"]))

    def test_review_below_category_floor_blocks(self):
        value = payload()
        value["candidates"][0]["reviews"][1]["scorecard"]["novelty"] = 6
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("novelty" in item for item in result["candidate_reviews"][0]["failures"]))

    def test_requires_three_to_twelve_source_bound_story_beats(self):
        value = payload()
        value["candidates"][0]["story_beats"] = value["candidates"][0]["story_beats"][:2]
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "story_beats must contain 3-12 source-bound beats",
            result["candidate_reviews"][0]["failures"],
        )

        value = payload()
        template = value["candidates"][0]["story_beats"][0]
        value["candidates"][0]["story_beats"] = [
            {
                **template,
                "beat": f"Distinct beat {index}",
                "source_quote": f"word {'word ' * index}".strip(),
            }
            for index in range(13)
        ]
        result = run_playoff(value)
        self.assertIn(
            "story_beats must contain 3-12 source-bound beats",
            result["candidate_reviews"][0]["failures"],
        )

    def test_story_beats_must_be_distinct(self):
        value = payload()
        value["candidates"][0]["story_beats"][1] = copy.deepcopy(
            value["candidates"][0]["story_beats"][0]
        )
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "story_beats must be distinct in both beat and source evidence",
            result["candidate_reviews"][0]["failures"],
        )

    def test_story_beat_quote_must_come_from_named_source(self):
        value = payload()
        other = source("other")
        value["candidates"][0]["sources"].append(other)
        value["candidates"][0]["story_beats"][0]["source_quote"] = (
            "other opening witness noticed the locked basement door"
        )
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "story_beats[0].source_quote must be an exact quote from the named source_id",
            result["candidate_reviews"][0]["failures"],
        )

    def test_story_beat_source_id_must_name_candidate_source(self):
        value = payload()
        value["candidates"][0]["story_beats"][0]["source_id"] = "unknown"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "story_beats[0].source_id must name an exact candidate source",
            result["candidate_reviews"][0]["failures"],
        )

    def test_originality_plan_requires_all_source_bound_directions(self):
        for field in ("editorial_frame", "visual_direction", "sound_direction"):
            with self.subTest(field=field):
                value = payload()
                value["candidates"][0]["originality_plan"][field]["direction"] = ""
                result = run_playoff(value)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn(
                    f"originality_plan.{field}.direction is required",
                    result["candidate_reviews"][0]["failures"],
                )

    def test_originality_quote_must_come_from_named_source(self):
        value = payload()
        other = source("other")
        value["candidates"][0]["sources"].append(other)
        value["candidates"][0]["originality_plan"]["visual_direction"][
            "source_quote"
        ] = "other middle revealed the warning had a different meaning"
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn(
            "originality_plan.visual_direction.source_quote must be an exact quote from the named source_id",
            result["candidate_reviews"][0]["failures"],
        )

    def test_generic_creative_evidence_cannot_anchor_invented_directions(self):
        value = payload()
        candidate_value = value["candidates"][0]
        candidate_value["story_beats"] = [
            {
                "beat": direction,
                "source_id": "aaa",
                "source_quote": quote,
            }
            for direction, quote in (
                ("Вымышленное признание президента", "word"),
                ("Вымышленная полицейская погоня", "word word"),
                ("Вымышленный судебный процесс", "word word word"),
            )
        ]
        for field, direction in (
            ("editorial_frame", "Строить выпуск вокруг вымышленного преступления"),
            ("visual_direction", "Показывать вымышленную полицейскую погоню"),
            ("sound_direction", "Добавить звуки вымышленного судебного процесса"),
        ):
            candidate_value["originality_plan"][field] = {
                "direction": direction,
                "source_id": "aaa",
                "source_quote": "word",
            }
        result = run_playoff(value)
        self.assertEqual(result["status"], "BLOCKED")
        failures = result["candidate_reviews"][0]["failures"]
        self.assertTrue(
            any("too generic to prove the creative direction" in item for item in failures)
        )

    def test_playoff_hash_binds_creative_plan_deterministically(self):
        first = run_playoff(payload())
        value = payload()
        value["candidates"][1]["originality_plan"]["editorial_frame"][
            "direction"
        ] = "Другой редакционный ракурс, всё ещё привязанный к источнику"
        second = run_playoff(value)
        self.assertEqual(first["status"], "READY_FOR_SCRIPTING")
        self.assertEqual(second["status"], "READY_FOR_SCRIPTING")
        self.assertNotEqual(
            first["candidate_reviews"][1]["creative_plan_sha256"],
            second["candidate_reviews"][1]["creative_plan_sha256"],
        )
        self.assertNotEqual(first["playoff_sha256"], second["playoff_sha256"])

    def test_playoff_hash_binds_exact_packaging_and_full_candidate_input(self):
        first_payload = payload()
        first = run_playoff(first_payload)
        second_payload = payload()
        second_payload["candidates"][1]["packaging_options"][0][
            "youtube_title"
        ] = "Другой честный заголовок"
        second = run_playoff(second_payload)
        self.assertEqual(first["status"], "READY_FOR_SCRIPTING")
        self.assertEqual(second["status"], "READY_FOR_SCRIPTING")
        self.assertNotEqual(
            first["winner"]["packaging_options_sha256"],
            second["winner"]["packaging_options_sha256"],
        )
        self.assertNotEqual(
            first["winner"]["candidate_contract_sha256"],
            second["winner"]["candidate_contract_sha256"],
        )
        self.assertNotEqual(first["playoff_input_sha256"], second["playoff_input_sha256"])
        self.assertNotEqual(first["playoff_sha256"], second["playoff_sha256"])

    def test_creative_and_playoff_hashes_are_repeatable(self):
        value = payload()
        first = run_playoff(value)
        second = run_playoff(copy.deepcopy(value))
        self.assertEqual(first["playoff_sha256"], second["playoff_sha256"])
        self.assertEqual(
            first["candidate_reviews"][0]["creative_plan_sha256"],
            second["candidate_reviews"][0]["creative_plan_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
