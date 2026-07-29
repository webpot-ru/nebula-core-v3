import unittest

from acc1_editorial_motion import (
    EditorialMotionError,
    build_editorial_motion_contract,
    verify_bound_payload,
)
from acc1_visual_contract import (
    CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
    EDITORIAL_MOTION_STYLE_PROFILE,
    FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    select_format_visual_system_v3_panel_grammar,
)


def asset(
    family: str, role: str, module: str, token: str, *,
    story_family: str | None = None, page_layout: str | None = None,
    panel_grammar: str | None = None, panel_count: int | None = None,
    panel_beat_role: str | None = None,
) -> dict:
    return {
        "kind": "generated_image",
        "local_path": f"{family}-{role}.png",
        "sha256": token * 64,
        "asset_family_id": family,
        "layer_role": role,
        "motion_module": module,
        "source_excerpt_sha256": "e" * 64,
        "factual_text_allowed": False,
        "story_family": story_family,
        "page_layout": page_layout,
        "panel_grammar": panel_grammar,
        "panel_count": panel_count,
        "panel_beat_role": panel_beat_role,
    }


class EditorialMotionContractTests(unittest.TestCase):
    @staticmethod
    def _timing(text: str, duration: float) -> dict:
        words = text.split()
        return {
            "duration_sec": duration,
            "timing_source": "local",
            "words": [
                {"word": word, "start": round(index * duration / len(words), 3), "end": round((index + 1) * duration / len(words), 3)}
                for index, word in enumerate(words)
            ],
        }

    def test_builds_exact_bound_seek_safe_scenes(self):
        words = [f"слово{index}" for index in range(80)]
        text = " ".join(words)
        timing_words = [
            {
                "word": word,
                "start": index,
                "end": index + 1,
                "timing_source": "ai33",
            }
            for index, word in enumerate(words)
        ]
        assets = [
            asset("pack-a", "hero_plate", "living_photo_depth", "a"),
            asset("pack-a", "detail_plate", "living_photo_depth", "b"),
            asset("pack-b", "hero_plate", "evidence_transform", "c"),
            asset("pack-b", "detail_plate", "evidence_transform", "d"),
        ]
        result = build_editorial_motion_contract(
            narration_segments=[{
                "segment_id": "story_one",
                "kind": "story",
                "voice_role": "narrator",
                "text": text,
            }],
            segment_timings={
                "story_one": {
                    "duration_sec": 80.0,
                    "words": timing_words,
                    "timing_source": "ai33",
                },
            },
            story_assets={"story_one": assets},
            story_metadata={"story_one": {
                "story_index": 1,
                "title": "Тест",
                "scene_titles": ["СЦЕНА А", "СЦЕНА Б"],
            }},
            final_audio_duration_sec=80.0,
        )
        scenes = result["scenes"]
        self.assertEqual(len(scenes), 2)
        self.assertEqual(
            [scene["story_title"] for scene in scenes], ["СЦЕНА А", "СЦЕНА Б"],
        )
        self.assertEqual(" ".join(scene["narration_text"] for scene in scenes), text)
        self.assertTrue(all(scene["motion"]["seek_safe"] for scene in scenes))
        self.assertTrue(all(
            scene["style_profile"] == EDITORIAL_MOTION_STYLE_PROFILE
            for scene in scenes
        ))
        self.assertEqual(
            result["motion_plan"]["style_profile"], EDITORIAL_MOTION_STYLE_PROFILE,
        )
        self.assertTrue(verify_bound_payload(result["motion_plan"], "motion_plan_sha256"))
        self.assertTrue(verify_bound_payload(result["caption_track"], "caption_track_sha256"))

    def test_scene_titles_must_match_scene_count(self):
        words = [f"слово{index}" for index in range(80)]
        text = " ".join(words)
        assets = [
            asset("pack-a", "hero_plate", "living_photo_depth", "a"),
            asset("pack-a", "detail_plate", "living_photo_depth", "b"),
            asset("pack-b", "hero_plate", "evidence_transform", "c"),
            asset("pack-b", "detail_plate", "evidence_transform", "d"),
        ]
        with self.assertRaisesRegex(EditorialMotionError, "scene_titles"):
            build_editorial_motion_contract(
                narration_segments=[{
                    "segment_id": "story_one",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": text,
                }],
                segment_timings={"story_one": {
                    "duration_sec": 80.0,
                    "timing_source": "local",
                    "words": [
                        {"word": word, "start": index, "end": index + 1}
                        for index, word in enumerate(words)
                    ],
                }},
                story_assets={"story_one": assets},
                story_metadata={"story_one": {
                    "story_index": 1,
                    "scene_titles": ["ТОЛЬКО ОДНА"],
                }},
                final_audio_duration_sec=80.0,
            )

    def test_ink_gouache_contract_preserves_family_and_layout(self):
        words = [f"слово{index}" for index in range(20)]
        text = " ".join(words)
        assets = [
            asset(
                "pack-a", role, "living_photo_depth", token,
                story_family="work", page_layout="hero_left_details_right",
            )
            for role, token in (("hero_plate", "a"), ("detail_plate", "b"))
        ]
        result = build_editorial_motion_contract(
            narration_segments=[{
                "segment_id": "story_one", "kind": "story",
                "voice_role": "narrator", "text": text,
            }],
            segment_timings={"story_one": {
                "duration_sec": 20.0, "timing_source": "local",
                "words": [
                    {"word": word, "start": index, "end": index + 1}
                    for index, word in enumerate(words)
                ],
            }},
            story_assets={"story_one": assets},
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=20.0,
            style_profile=INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
        )
        scene = result["scenes"][0]
        self.assertEqual(scene["story_family"], "work")
        self.assertEqual(scene["page_layout"], "hero_left_details_right")
        self.assertEqual(
            result["motion_plan"]["style_profile"],
            INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
        )

    def test_incomplete_asset_family_fails_closed(self):
        with self.assertRaisesRegex(EditorialMotionError, "exactly"):
            build_editorial_motion_contract(
                narration_segments=[{
                    "segment_id": "story_one",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": "один два три четыре",
                }],
                segment_timings={
                    "story_one": {
                        "duration_sec": 20.0,
                        "words": [
                            {"word": word, "start": index * 5, "end": (index + 1) * 5}
                            for index, word in enumerate("один два три четыре".split())
                        ],
                        "timing_source": "ai33",
                    },
                },
                story_assets={
                    "story_one": [
                        asset("pack-a", "hero_plate", "living_photo_depth", "a"),
                    ],
                },
                story_metadata={"story_one": {"story_index": 1}},
                final_audio_duration_sec=20.0,
            )

    def test_cinematic_ink_webtoon_uses_every_paid_asset_pack(self):
        words = [f"слово{index}" for index in range(60)]
        text = " ".join(words)
        layouts = (
            "hero_left_details_right", "phone_portal_insets", "message_cascade",
        )
        assets = []
        for index, layout in enumerate(layouts):
            for role in ("hero_plate", "detail_plate"):
                assets.append(asset(
                    f"pack-{index}", role, "living_photo_depth", str(index + 1),
                    story_family="relationships", page_layout=layout,
                ))
        result = build_editorial_motion_contract(
            narration_segments=[{
                "segment_id": "story_one", "kind": "story",
                "voice_role": "narrator", "text": text,
            }],
            segment_timings={"story_one": {
                "duration_sec": 60.0, "timing_source": "local",
                "words": [
                    {"word": word, "start": index, "end": index + 1}
                    for index, word in enumerate(words)
                ],
            }},
            story_assets={"story_one": assets},
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=60.0,
            style_profile=CINEMATIC_INK_WEBTOON_STYLE_PROFILE,
        )
        self.assertEqual(len(result["scenes"]), 3)
        self.assertEqual(
            [scene["asset_family_id"] for scene in result["scenes"]],
            ["pack-0", "pack-1", "pack-2"],
        )

    def test_mid_story_cta_is_short_service_scene(self):
        story_text = " ".join(f"слово{index}" for index in range(40))
        cta_text = "На чьей стороне вы сейчас? Напишите в комментариях. Продолжаем."
        assets = [
            asset("pack-a", "hero_plate", "living_photo_depth", "a"),
            asset("pack-a", "detail_plate", "living_photo_depth", "b"),
        ]
        result = build_editorial_motion_contract(
            narration_segments=[
                {"segment_id": "story_one", "kind": "story", "voice_role": "narrator", "text": story_text},
                {"segment_id": "mid_story_cta", "kind": "mid_story_cta", "voice_role": "narrator", "text": cta_text},
            ],
            segment_timings={
                "story_one": self._timing(story_text, 20.0),
                "mid_story_cta": self._timing(cta_text, 6.0),
            },
            story_assets={"story_one": assets},
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=26.0,
        )
        self.assertEqual([scene["presentation"] for scene in result["scenes"]], [
            "story", "mid_story_cta",
        ])
        self.assertEqual(result["scenes"][1]["motion"]["module"], "evidence_transform")

    def test_long_intro_uses_multiple_short_existing_service_scenes(self):
        intro_text = " ".join(f"вступление{index}" for index in range(20))
        story_text = " ".join(f"слово{index}" for index in range(40))
        assets = [
            asset("pack-a", "hero_plate", "living_photo_depth", "a"),
            asset("pack-a", "detail_plate", "living_photo_depth", "b"),
            asset("pack-b", "hero_plate", "evidence_transform", "c"),
            asset("pack-b", "detail_plate", "evidence_transform", "d"),
        ]
        result = build_editorial_motion_contract(
            narration_segments=[
                {
                    "segment_id": "intro",
                    "kind": "intro",
                    "voice_role": "narrator",
                    "text": intro_text,
                },
                {
                    "segment_id": "story_one",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": story_text,
                },
            ],
            segment_timings={
                "intro": self._timing(intro_text, 30.0),
                "story_one": self._timing(story_text, 20.0),
            },
            story_assets={"story_one": assets},
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=50.0,
        )
        intro_scenes = [
            scene for scene in result["scenes"]
            if scene["presentation"] == "intro"
        ]
        self.assertEqual(len(intro_scenes), 2)
        self.assertEqual(
            [scene["asset_family_id"] for scene in intro_scenes],
            ["pack-a", "pack-b"],
        )
        self.assertEqual(
            [scene["duration_sec"] for scene in intro_scenes],
            [15.0, 15.0],
        )
        self.assertTrue(all(
            scene["motion"]["module"] == "nested_collage_zoom"
            for scene in intro_scenes
        ))
        self.assertEqual(
            " ".join(scene["narration_text"] for scene in intro_scenes),
            intro_text,
        )

    def test_long_v3_intro_reuses_one_pack_with_distinct_semantic_passes(self):
        intro_text = " ".join(f"вступление{index}" for index in range(20))
        story_text = " ".join(f"слово{index}" for index in range(40))
        grammar = select_format_visual_system_v3_panel_grammar("BUNDLE", 1, 1)
        assets = [
            asset(
                "pack-a",
                role,
                "living_photo_depth",
                token,
                story_family="relationships",
                page_layout="bundle_story_opener",
                panel_grammar=grammar["id"],
                panel_count=grammar["panel_count"],
                panel_beat_role=grammar["beat_role"],
            )
            for role, token in (
                ("hero_plate", "a"),
                ("detail_plate", "b"),
            )
        ]
        result = build_editorial_motion_contract(
            narration_segments=[
                {
                    "segment_id": "intro",
                    "kind": "intro",
                    "voice_role": "narrator",
                    "text": intro_text,
                },
                {
                    "segment_id": "story_one",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": story_text,
                },
            ],
            segment_timings={
                "intro": self._timing(intro_text, 30.0),
                "story_one": self._timing(story_text, 20.0),
            },
            story_assets={"story_one": assets},
            story_metadata={"story_one": {
                "story_index": 1,
                "format_id": "BUNDLE",
            }},
            final_audio_duration_sec=50.0,
            style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        )
        intro_scenes = [
            scene for scene in result["scenes"]
            if scene["presentation"] == "intro"
        ]
        self.assertEqual(
            [scene["asset_family_id"] for scene in intro_scenes],
            ["pack-a", "pack-a"],
        )
        self.assertEqual(
            [scene["semantic_camera_pass"] for scene in intro_scenes],
            ["overview", "semantic"],
        )
        self.assertEqual(
            [scene["duration_sec"] for scene in intro_scenes],
            [15.0, 15.0],
        )
        self.assertNotEqual(
            intro_scenes[0]["camera_path"],
            intro_scenes[1]["camera_path"],
        )
        self.assertEqual(
            intro_scenes[0]["camera_path"][1]["kind"],
            "page_overview_hold",
        )
        self.assertEqual(
            intro_scenes[1]["camera_path"][1]["kind"],
            "semantic_panel_focus",
        )
        self.assertEqual(
            " ".join(scene["narration_text"] for scene in intro_scenes),
            intro_text,
        )

    def test_legacy_long_intro_still_fails_closed_without_enough_packs(self):
        intro_text = " ".join(f"вступление{index}" for index in range(20))
        story_text = " ".join(f"слово{index}" for index in range(40))
        assets = [
            asset("pack-a", "hero_plate", "living_photo_depth", "a"),
            asset("pack-a", "detail_plate", "living_photo_depth", "b"),
            asset("pack-b", "hero_plate", "evidence_transform", "c"),
            asset("pack-b", "detail_plate", "evidence_transform", "d"),
        ]
        with self.assertRaisesRegex(
            EditorialMotionError,
            "editorial intro requires 3 existing asset packs but has 2",
        ):
            build_editorial_motion_contract(
                narration_segments=[
                    {
                        "segment_id": "intro",
                        "kind": "intro",
                        "voice_role": "narrator",
                        "text": intro_text,
                    },
                    {
                        "segment_id": "story_one",
                        "kind": "story",
                        "voice_role": "narrator",
                        "text": story_text,
                    },
                ],
                segment_timings={
                    "intro": self._timing(intro_text, 30.1),
                    "story_one": self._timing(story_text, 20.0),
                },
                story_assets={"story_one": assets},
                story_metadata={"story_one": {"story_index": 1}},
                final_audio_duration_sec=50.1,
            )

    def test_v3_thread_preserves_global_prompt_response_sequence_and_voices(self):
        prompt_grammar = select_format_visual_system_v3_panel_grammar(
            "THREAD", 1, 2,
        )
        response_grammar = select_format_visual_system_v3_panel_grammar(
            "THREAD", 2, 2,
        )

        def pack(source_id, grammar, *, layout):
            return [
                asset(
                    source_id,
                    role,
                    "living_photo_depth",
                    token,
                    story_family="confessions",
                    page_layout=layout,
                    panel_grammar=grammar["id"],
                    panel_count=grammar["panel_count"],
                    panel_beat_role=grammar["beat_role"],
                )
                for role, token in (
                    ("hero_plate", "a"),
                    ("detail_plate", "b"),
                )
            ]

        prompt_text = "Какой секрет вы скрывали дольше всего?"
        response_text = "Я годами скрывала от семьи одну неловкую правду."

        def timing(text):
            words = text.split()
            step = 20.0 / len(words)
            return {
                "duration_sec": 20.0,
                "timing_source": "local",
                "words": [
                    {
                        "word": word,
                        "start": index * step,
                        "end": (index + 1) * step,
                    }
                    for index, word in enumerate(words)
                ],
            }

        result = build_editorial_motion_contract(
            narration_segments=[
                {
                    "segment_id": "story_prompt",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": prompt_text,
                },
                {
                    "segment_id": "story_response",
                    "kind": "story",
                    "voice_role": "comment",
                    "text": response_text,
                },
            ],
            segment_timings={
                "story_prompt": timing(prompt_text),
                "story_response": timing(response_text),
            },
            story_assets={
                "story_prompt": pack(
                    "prompt-pack",
                    prompt_grammar,
                    layout="thread_prompt_anchor",
                ),
                "story_response": pack(
                    "response-pack",
                    response_grammar,
                    layout="thread_response_vignette",
                ),
            },
            story_metadata={
                "story_prompt": {
                    "story_index": 1,
                    "format_id": "THREAD",
                    "format_scene_number": 1,
                    "format_scene_count": 2,
                    "source_role": "prompt",
                },
                "story_response": {
                    "story_index": 2,
                    "format_id": "THREAD",
                    "format_scene_number": 2,
                    "format_scene_count": 2,
                    "source_role": "response",
                    "thread_response_number": 1,
                    "editorial_role": "awkward confession",
                },
            },
            final_audio_duration_sec=40.0,
            style_profile=FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
        )
        prompt, response = result["scenes"]
        self.assertEqual(
            [prompt["scene_number"], response["scene_number"]],
            [1, 2],
        )
        self.assertEqual(
            [prompt["scene_count"], response["scene_count"]],
            [2, 2],
        )
        self.assertEqual(prompt["source_role"], "prompt")
        self.assertEqual(prompt["voice_role"], "narrator")
        self.assertEqual(response["source_role"], "response")
        self.assertEqual(response["voice_role"], "comment")
        self.assertEqual(response["thread_response_number"], 1)
        self.assertEqual(response["editorial_role"], "awkward confession")
        self.assertEqual(prompt["panel_grammar"], prompt_grammar["id"])
        self.assertEqual(response["panel_grammar"], response_grammar["id"])


if __name__ == "__main__":
    unittest.main()
