import copy
import unittest

from acc1_episode_packaging import (
    EpisodePackagingError,
    build_prompt,
    build_thumbnail_prompt,
    build_youtube_description,
    generate_packaging,
    validate_packaging,
)


def script():
    body = "точный источник подробно подтверждает неожиданную развязку истории"
    return {
        "episode_plan_sha256": "a" * 64,
        "episode_format": "SAGA",
        "pillar": "relationships_family",
        "title_ru": "История",
        "truth_disclosure_ru": "Личный рассказ с Reddit не подтверждён независимо.",
        "stories": [
            {
                "source_snapshot": {
                    "post_id": "abc",
                    "body": body,
                    "source_url": "https://www.reddit.com/r/test/comments/abc/topic/",
                }
            }
        ],
    }


def valid_payload():
    disclosure = "Личный рассказ с Reddit не подтверждён независимо."
    url = "https://www.reddit.com/r/test/comments/abc/topic/"
    return {
        "packaging_options": [
            {
                "youtube_title": f"Заголовок {index}",
                "thumbnail_text": f"ТЕКСТ {index}",
                "first_screen_promise": f"Обещание {index}",
                "angle": f"angle-{index}",
                "source_id": "abc",
                "source_backing": "точный источник подробно подтверждает неожиданную развязку истории",
            }
            for index in range(3)
        ],
        "selected_option_index": 1,
        "youtube_description": build_youtube_description(disclosure, [url]),
        "thumbnail_prompt": build_thumbnail_prompt(
            "точный источник подробно подтверждает неожиданную развязку истории"
        ),
        "thumbnail_source_id": "abc",
        "thumbnail_source_backing": "точный источник подробно подтверждает неожиданную развязку истории",
        "language": "ru",
        "risk_flags": [],
    }


def locked_playoff():
    return {"winner_packaging_options": copy.deepcopy(valid_payload()["packaging_options"])}


class EpisodePackagingTests(unittest.TestCase):
    def test_valid_source_bound_packaging(self):
        self.assertEqual(validate_packaging(valid_payload(), script()), [])

    def test_description_requires_disclosure_and_source_url(self):
        payload = valid_payload()
        payload["youtube_description"] = "Описание"
        failures = validate_packaging(payload, script())
        self.assertTrue(any("truth disclosure" in item for item in failures))
        self.assertTrue(any("source URL" in item for item in failures))

    def test_selected_index_is_checked(self):
        payload = valid_payload()
        payload["selected_option_index"] = 3
        self.assertTrue(any("selected_option_index" in item for item in validate_packaging(payload, script())))

    def test_provider_output_fails_closed(self):
        def provider(**_kwargs):
            return {"packaging_options": []}

        with self.assertRaises(EpisodePackagingError):
            generate_packaging(script(), {}, provider=provider)

    def test_generation_adds_plan_binding(self):
        result = generate_packaging(script(), {}, provider=lambda **_kwargs: valid_payload())
        self.assertEqual(result["episode_plan_sha256"], "a" * 64)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["publication_authorized"])

    def test_locked_winner_options_are_returned_exactly(self):
        playoff = locked_playoff()
        result = generate_packaging(
            script(),
            playoff,
            provider=lambda **_kwargs: {"selected_option_index": 1},
        )
        self.assertEqual(result["packaging_options"], playoff["winner_packaging_options"])
        self.assertEqual(result["selected_option_index"], 1)
        self.assertEqual(
            result["thumbnail_source_backing"],
            playoff["winner_packaging_options"][1]["source_backing"],
        )
        self.assertEqual(
            result["thumbnail_prompt"],
            build_thumbnail_prompt(playoff["winner_packaging_options"][1]["source_backing"]),
        )
        self.assertEqual(result["risk_flags"], [])
        prompt = build_prompt(script(), playoff)
        self.assertIn("immutable lock", prompt)
        self.assertIn('"youtube_title": "Заголовок 0"', prompt)
        self.assertIn('{"selected_option_index": 0}', prompt)
        self.assertNotIn('"youtube_description": ""', prompt)

    def test_locked_winner_options_ignore_provider_authored_deterministic_fields(self):
        playoff = locked_playoff()
        result = generate_packaging(
            script(),
            playoff,
            provider=lambda **_kwargs: {
                "selected_option_index": 2,
                "youtube_description": "invented",
                "thumbnail_prompt": "invented",
                "risk_flags": ["invented"],
            },
        )
        self.assertEqual(
            result["youtube_description"],
            build_youtube_description(
                script()["truth_disclosure_ru"],
                ["https://www.reddit.com/r/test/comments/abc/topic/"],
            ),
        )
        self.assertEqual(result["risk_flags"], [])

    def test_locked_winner_selection_must_be_valid(self):
        with self.assertRaisesRegex(EpisodePackagingError, "selected_option_index"):
            generate_packaging(
                script(),
                locked_playoff(),
                provider=lambda **_kwargs: {"selected_option_index": 3},
            )

    def test_locked_winner_options_reject_any_provider_rewrite(self):
        playoff = locked_playoff()
        payload = valid_payload()
        payload["packaging_options"][0]["youtube_title"] = "Переписанный заголовок"
        failures = validate_packaging(payload, script(), playoff)
        self.assertIn(
            "packaging_options must exactly equal playoff.winner_packaging_options",
            failures,
        )

    def test_malformed_lock_blocks_before_provider_call(self):
        called = False

        def provider(**_kwargs):
            nonlocal called
            called = True
            return valid_payload()

        with self.assertRaisesRegex(EpisodePackagingError, "exactly three objects"):
            generate_packaging(
                script(),
                {"winner_packaging_options": [{"youtube_title": "one"}]},
                provider=provider,
            )
        self.assertFalse(called)

    def test_thumbnail_quote_must_come_from_named_source(self):
        value = script()
        value["stories"].append(
            {
                "source_snapshot": {
                    "post_id": "def",
                    "body": "другая точная цитата подробно описывает отдельную сцену",
                    "source_url": "https://www.reddit.com/r/test/comments/def/topic/",
                }
            }
        )
        payload = valid_payload()
        payload["youtube_description"] = build_youtube_description(
            value["truth_disclosure_ru"],
            [
                "https://www.reddit.com/r/test/comments/abc/topic/",
                "https://www.reddit.com/r/test/comments/def/topic/",
            ],
        )
        payload["thumbnail_source_backing"] = "другая точная цитата подробно описывает отдельную сцену"
        payload["thumbnail_prompt"] = build_thumbnail_prompt(
            "другая точная цитата подробно описывает отдельную сцену"
        )
        failures = validate_packaging(payload, value)
        self.assertIn(
            "thumbnail_source_backing must be an exact quote from thumbnail_source_id",
            failures,
        )

    def test_thumbnail_prompt_must_carry_quote_and_safety_instructions(self):
        payload = valid_payload()
        payload["thumbnail_prompt"] = "16:9 scene with clean left space"
        failures = validate_packaging(payload, script())
        self.assertIn(
            "thumbnail_prompt must contain thumbnail_source_backing verbatim",
            failures,
        )
        self.assertTrue(any("no-text/no-logo/no-gore" in item for item in failures))

    def test_generic_quote_cannot_anchor_an_invented_thumbnail_scene(self):
        payload = valid_payload()
        payload["thumbnail_source_backing"] = "истории"
        payload["thumbnail_prompt"] = (
            "A president confessing to a crime, истории, clean left space; "
            "no rendered text, no logos, no gore"
        )
        failures = validate_packaging(payload, script())
        self.assertIn("thumbnail_source_backing is too generic", failures)
        self.assertIn(
            "thumbnail_prompt must equal the deterministic source-bound template",
            failures,
        )

    def test_meaningful_quote_cannot_be_attached_to_an_invented_scene(self):
        payload = valid_payload()
        quote = payload["thumbnail_source_backing"]
        payload["thumbnail_prompt"] = (
            f"A president confessing to a crime, {quote}; "
            "no rendered text, no logos, no gore"
        )
        self.assertIn(
            "thumbnail_prompt must equal the deterministic source-bound template",
            validate_packaging(payload, script()),
        )

    def test_thumbnail_source_id_must_identify_script_source(self):
        payload = valid_payload()
        payload["thumbnail_source_id"] = "missing"
        failures = validate_packaging(payload, script())
        self.assertIn("thumbnail_source_id must name exactly one script source", failures)

    def test_description_cannot_append_an_unverified_factual_claim(self):
        payload = valid_payload()
        payload["youtube_description"] += (
            "\nПрезидент признался в преступлении, это подтвержденный факт."
        )
        self.assertIn(
            "youtube_description must equal the deterministic neutral source template",
            validate_packaging(payload, script(), locked_playoff()),
        )


if __name__ == "__main__":
    unittest.main()
