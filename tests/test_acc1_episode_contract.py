import hashlib
import unittest

from acc1_episode_contract import (
    build_intro_contract,
    build_mid_story_cta_contract,
    build_outro_prompt,
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
    mid_story_cta_contract = build_mid_story_cta_contract(
        episode_format="SAGA",
        pillar="strange_dark_unexplained",
        anchor_source=snap,
        anchor_index=1,
        source_count=1,
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
        "mid_story_cta_contract": mid_story_cta_contract,
        "mid_story_cta_ru": mid_story_cta_contract["cta_ru"],
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
        "translation_final_adjudication_contract": {
            "version": 1,
            "format": "SAGA",
            "thread_limit": 0,
            "thread_used": 0,
            "basis": "approved_openai_call_cap_headroom_v1",
            "automatic_retries": 0,
            "publication_authorized": False,
        },
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

    def test_bundle_intro_uses_compact_source_bound_first_story_label(self):
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
            texts["first_story_cue"],
            "История первая. «Мой сосед — маньяк».",
        )
        self.assertEqual([item["kind"] for item in contract["parts"]], [
            "cold_open", "truth_disclosure", "first_story_cue",
        ])

    def test_thread_intro_uses_response_count_and_topic_label(self):
        contract = build_intro_contract(
            cold_open=self._intro_cold_open(),
            episode_format="THREAD",
            pillar="confessions_awkward_taboo",
            source_count=14,
            response_count=13,
            first_title_ru="Какую тайну вы скрывали годами?",
            truth_disclosure=(
                "Это личный рассказ пользователя Reddit, не подтверждённый независимо."
            ),
        )
        texts = {item["kind"]: item["text"] for item in contract["parts"]}
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

    def test_intro_has_exact_compact_approved_order(self):
        plan, playoff, script = fixtures()
        kinds = [item["kind"] for item in script["intro_contract"]["parts"]]
        self.assertEqual(kinds, [
            "cold_open", "truth_disclosure", "first_story_cue",
        ])
        self.assertEqual(validate_episode_script(script, plan=plan, playoff=playoff)["status"], "PASS")

    def test_unverified_named_sponsor_tamper_blocks(self):
        plan, playoff, script = fixtures()
        script["intro_contract"]["parts"].append({
            "kind": "support_thanks", "text": "Спасибо спонсору Ивану за оплату этого выпуска.",
        })
        script["intro_ru"] = " ".join(
            item["text"] for item in script["intro_contract"]["parts"]
        )
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "intro_contract must exactly match the approved deterministic structure",
            result["failures"],
        )

    def test_dark_call_outro_is_specific_without_claiming_source_is_real(self):
        result = build_outro_prompt(
            episode_format="SAGA",
            pillar="strange_dark_unexplained",
            first_source={"title": "A 911 dispatcher call", "body": "The phone rang."},
        )
        self.assertEqual(
            result,
            "Вы бы ответили на такой звонок? А если у вас есть история, от которой до сих пор не по себе, расскажите её в комментариях.",
        )

    def test_mid_story_cta_is_source_bound_and_deterministic(self):
        snap = snapshot(source_id="work", words=20)
        contract = build_mid_story_cta_contract(
            episode_format="BUNDLE",
            pillar="work_money_justice",
            anchor_source=snap,
            anchor_index=1,
            source_count=2,
        )
        self.assertEqual(contract["source_anchor"]["source_id"], "work")
        self.assertIn(contract["source_anchor"]["source_quote"], snap["body"])
        self.assertEqual(
            contract["cta_ru"],
            "Вы бы уже вмешались или сначала собрали доказательства? Напишите в комментариях. Если нравятся полные истории без выдуманных продолжений — подписывайтесь. Продолжаем.",
        )

    def test_mid_story_cta_tamper_blocks(self):
        plan, playoff, script = fixtures()
        script["mid_story_cta_ru"] = "Поставьте лайк и продолжим."
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "mid_story_cta_ru must exactly match the deterministic CTA contract",
            result["failures"],
        )

    def test_spoken_title_says_911_digit_by_digit_and_avoids_repeating_payoff(self):
        contract = build_intro_contract(
            cold_open=self._intro_cold_open(),
            episode_format="SAGA",
            pillar="strange_dark_unexplained",
            source_count=1,
            response_count=0,
            first_title_ru=(
                "Мой начальник дал мне одно правило как диспетчеру 911: "
                "если звонят из старого дома, не отвечай."
            ),
            truth_disclosure="Это художественная история с Reddit.",
        )
        self.assertIn("девять один один", contract["intro_ru"])
        self.assertNotIn("если звонят из старого дома", contract["intro_ru"])

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

    def test_translation_final_adjudication_contract_is_fail_closed(self):
        plan, playoff, script = fixtures()
        script["translation_final_adjudication_contract"]["automatic_retries"] = 1
        result = validate_episode_script(script, plan=plan, playoff=playoff)
        self.assertIn(
            "translation final adjudication automatic retries must remain zero",
            result["failures"],
        )

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
