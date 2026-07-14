import hashlib
import unittest

from acc1_episode_contract import (
    DARK_BRAND_STING_RU,
    build_intro_contract,
    canonical_hash,
    truth_disclosure_ru,
    validate_episode_script,
)
from acc1_episode_manifest import disclosure_for_truth_mode


def snapshot(source_id="abc", words=2500):
    body = (f"{source_id} " + "word " * (words - 2) + "payoff").strip()
    return {
        "source_id": source_id,
        "post_id": source_id,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "source_url": f"https://www.reddit.com/r/test/comments/{source_id}/topic/",
        "author": f"author-{source_id}",
        "subreddit": "test",
        "truth_mode": "unverified_personal_account",
    }


def fixtures():
    snap = snapshot()
    normalized_source = {
        "post_id": snap["post_id"],
        "body_sha256": snap["body_sha256"],
        "truth_mode": snap["truth_mode"],
        "required_disclosure": disclosure_for_truth_mode(snap["truth_mode"]),
    }
    daily_plan = {
        "episode_key": "acc1/2026-07-14/pilot_03",
        "production_date": "2026-07-14",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "publication_authorized": False,
    }
    plan = {
        "version": 1,
        "status": "LOCKED",
        "channel_id": "acc1",
        "episode_key": "acc1/2026-07-14/pilot_03",
        "episode_date": "2026-07-14",
        "pilot_id": "pilot_03",
        "format": "SAGA",
        "pillar": "strange_dark_unexplained",
        "daily_plan_sha256": canonical_hash(daily_plan),
        "sources": [normalized_source],
        "truth_disclosure_contract": {
            "audible_once_per_episode": True,
            "metadata_visible_once_per_episode": True,
            "truth_mode": snap["truth_mode"],
            "text": normalized_source["required_disclosure"],
        },
        "artifact_bindings": {
            "queue_sha256": "1" * 64,
            "review_sha256": "2" * 64,
            "greenlight_sha256": "3" * 64,
            "config_sha256": "4" * 64,
        },
        "git_sha": "a" * 40,
        "provider_settings": {"gemini_model": "gemini-3.5-flash"},
        "publication_authorized": False,
    }
    plan["episode_plan_sha256"] = canonical_hash(plan)
    source_set = [{
        "source_id": snap["source_id"],
        "body_sha256": snap["body_sha256"],
        "source_url": snap["source_url"],
        "truth_mode": snap["truth_mode"],
        "role": "story",
    }]
    story_beats = [
        {"beat": "opening", "source_id": snap["source_id"], "source_quote": "abc word"},
        {"beat": "escalation", "source_id": snap["source_id"], "source_quote": "word word word"},
        {"beat": "payoff", "source_id": snap["source_id"], "source_quote": "word payoff"},
    ]
    originality_plan = {
        "editorial_frame": {
            "direction": "Frame the source conflict without adding facts",
            "source_id": snap["source_id"], "source_quote": "abc word",
        },
        "visual_direction": {
            "direction": "Use restrained source-bound scene changes",
            "source_id": snap["source_id"], "source_quote": "word word word",
        },
        "sound_direction": {
            "direction": "Build toward the preserved payoff",
            "source_id": snap["source_id"], "source_quote": "word payoff",
        },
    }
    cold_open = {
        "text": "Сначала дверь оставалась запертой, но затем свидетель услышал голос из подвала.",
        "source_id": snap["source_id"],
        "source_quote": "abc word",
    }
    playoff = {
        "status": "READY_FOR_SCRIPTING",
        "playoff_sha256": "b" * 64,
        "winner": {
            "source_set_sha256": canonical_hash(source_set),
            "creative_plan_sha256": canonical_hash({
                "story_beats": story_beats,
                "originality_plan": originality_plan,
            }),
            "cold_open_sha256": canonical_hash(cold_open),
        },
    }
    disclosure = truth_disclosure_ru({"unverified_personal_account"})
    intro_contract = build_intro_contract(
        cold_open=cold_open,
        episode_format="SAGA",
        pillar="strange_dark_unexplained",
        source_count=1,
        response_count=0,
        first_title_ru="История",
        truth_disclosure=disclosure,
    )
    script = {
        "episode_plan_sha256": plan["episode_plan_sha256"],
        "playoff_sha256": playoff["playoff_sha256"],
        "publication_authorized": False,
        "episode_format": "SAGA",
        "pilot_id": "pilot_03",
        "pillar": "strange_dark_unexplained",
        "title_ru": "Заголовок",
        "truth_disclosure_ru": disclosure,
        "intro_contract": intro_contract,
        "intro_ru": intro_contract["intro_ru"],
        "outro_ru": "Обсудим в комментариях.",
        "source_story_beats": story_beats,
        "originality_plan": originality_plan,
        "stories": [{
            "title_ru": "История",
            "narration_ru": "Полный перевод истории",
            "narration_role": "narrator",
            "source_snapshot": snap,
            "ending_preserved_evidence": "payoff",
            "translation_audit": {"review": {"verdict": "PASS"}},
        }],
    }
    return plan, playoff, script


class EpisodeContractTests(unittest.TestCase):
    @staticmethod
    def _intro_cold_open():
        return {
            "text": "Сначала сосед позвал детей к окну, а затем их отец увидел его сам.",
            "source_id": "source-1",
            "source_quote": "exact source evidence for the opening",
        }

    def test_bundle_intro_uses_exact_count_and_first_story_label(self):
        contract = build_intro_contract(
            cold_open=self._intro_cold_open(),
            episode_format="BUNDLE",
            pillar="relationships_family",
            source_count=5,
            response_count=0,
            first_title_ru="Мой сосед — маньяк",
            truth_disclosure="Это художественные истории с Reddit.",
        )
        texts = {item["kind"]: item["text"] for item in contract["parts"]}
        self.assertEqual(
            texts["episode_promise"],
            "Сегодня — пять законченных историй с Reddit.",
        )
        self.assertEqual(
            texts["first_story_cue"],
            "История первая. «Мой сосед — маньяк».",
        )
        self.assertIn("Устраивайтесь поудобнее", texts["brand_sting"])
        self.assertNotIn("Свет можно", texts["brand_sting"])

    def test_thread_intro_uses_response_count_and_topic_label(self):
        contract = build_intro_contract(
            cold_open=self._intro_cold_open(),
            episode_format="THREAD",
            pillar="confessions_awkward_taboo",
            source_count=9,
            response_count=8,
            first_title_ru="Какую тайну вы скрывали годами?",
            truth_disclosure=(
                "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
            ),
        )
        texts = {item["kind"]: item["text"] for item in contract["parts"]}
        self.assertEqual(
            texts["episode_promise"],
            "Сегодня — одна тема и восемь полных ответов с Reddit.",
        )
        self.assertEqual(
            texts["first_story_cue"],
            "Тема выпуска. «Какую тайну вы скрывали годами?»",
        )

    def test_valid_saga_passes(self):
        plan, playoff, script = fixtures()
        self.assertEqual(validate_episode_script(script, plan=plan, playoff=playoff)["status"], "PASS")

    def test_plan_binding_mismatch_blocks(self):
        plan, playoff, script = fixtures()
        script["episode_plan_sha256"] = "0" * 64
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn("episode script is not bound to the exact episode plan", result["failures"])

    def test_truth_disclosure_must_be_spoken(self):
        plan, playoff, script = fixtures()
        script["intro_ru"] = "Добро пожаловать."
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertTrue(any("spoken" in item for item in result["failures"]))

    def test_intro_has_exact_approved_order_and_dark_brand_sting(self):
        plan, playoff, script = fixtures()
        kinds = [item["kind"] for item in script["intro_contract"]["parts"]]
        self.assertEqual(kinds, [
            "cold_open", "episode_promise", "truth_disclosure", "source_note",
            "support_thanks", "brand_sting", "first_story_cue",
        ])
        self.assertEqual(script["intro_contract"]["parts"][5]["text"], DARK_BRAND_STING_RU)
        self.assertEqual(validate_episode_script(script, plan=plan, playoff=playoff)["status"], "PASS")

    def test_unverified_named_sponsor_tamper_blocks(self):
        plan, playoff, script = fixtures()
        script["intro_contract"]["parts"][4]["text"] = (
            "Спасибо спонсору Ивану за оплату этого выпуска."
        )
        script["intro_ru"] = " ".join(
            item["text"] for item in script["intro_contract"]["parts"]
        )
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "intro_contract must exactly match the approved deterministic structure",
            result["failures"],
        )

    def test_cold_open_tamper_after_playoff_blocks(self):
        plan, playoff, script = fixtures()
        script["intro_contract"]["cold_open"]["text"] = (
            "Сначала дверь открылась сама, а затем рассказчик увидел тень в подвале."
        )
        script["intro_contract"]["parts"][0]["text"] = script["intro_contract"]["cold_open"]["text"]
        script["intro_ru"] = " ".join(
            item["text"] for item in script["intro_contract"]["parts"]
        )
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "intro cold open does not match the topic-playoff winner",
            result["failures"],
        )

    def test_source_swap_after_playoff_blocks(self):
        plan, playoff, script = fixtures()
        script["stories"][0]["source_snapshot"] = snapshot("other")
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertTrue(any("playoff winner" in item for item in result["failures"]))

    def test_translation_requires_independent_pass(self):
        plan, playoff, script = fixtures()
        script["stories"][0]["translation_audit"]["review"]["verdict"] = "REVISE"
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertTrue(any("independent PASS" in item for item in result["failures"]))

    def test_creative_plan_tamper_after_playoff_blocks(self):
        plan, playoff, script = fixtures()
        script["originality_plan"]["sound_direction"]["direction"] = "generic sound"
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "episode script creative plan does not match the playoff winner",
            result["failures"],
        )

    def test_mixed_truth_modes_disclosure_is_invalid(self):
        with self.assertRaises(ValueError):
            truth_disclosure_ru({"fiction", "unverified_personal_account"})


if __name__ == "__main__":
    unittest.main()
