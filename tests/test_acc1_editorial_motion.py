import unittest

from acc1_editorial_motion import (
    EditorialMotionError,
    build_editorial_motion_contract,
    verify_bound_payload,
)
from acc1_visual_contract import (
    EDITORIAL_MOTION_STYLE_PROFILE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
)


def asset(
    family: str, role: str, module: str, token: str, *,
    story_family: str | None = None, page_layout: str | None = None,
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
    }


class EditorialMotionContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
