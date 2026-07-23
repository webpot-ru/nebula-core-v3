import unittest
import tempfile
from pathlib import Path

from acc1_cinematic_shots import (
    CinematicShotError,
    build_cinematic_contract,
    write_caption_srt,
)
from acc1_visual_contract import (
    ADULT_ANIMATION_FAMILY_STYLE_PROFILE,
    ADULT_ANIMATION_STYLE_PROFILES,
    CINEMATIC_STORY_MODE,
    DEFAULT_VISUAL_MODE,
    EDITORIAL_MOTION_MODE,
    REDDIT_PAGES_MODE,
    adult_animation_profile_for_pilot,
    resolve_visual_mode,
    select_adult_animation_layouts,
)


class VisualModeContractTests(unittest.TestCase):
    def test_default_mode_remains_reddit_pages(self):
        self.assertEqual(DEFAULT_VISUAL_MODE, REDDIT_PAGES_MODE)
        self.assertEqual(resolve_visual_mode(), REDDIT_PAGES_MODE)

    def test_cinematic_mode_is_explicit_and_unknown_modes_fail_closed(self):
        self.assertEqual(
            resolve_visual_mode(CINEMATIC_STORY_MODE),
            CINEMATIC_STORY_MODE,
        )
        with self.assertRaisesRegex(ValueError, "visual_mode"):
            resolve_visual_mode("cinematic-ish")

    def test_editorial_motion_mode_is_explicit(self):
        self.assertEqual(resolve_visual_mode(EDITORIAL_MOTION_MODE), EDITORIAL_MOTION_MODE)

    def test_six_adult_animation_profiles_are_pilot_bound_and_layouts_vary_by_source(self):
        self.assertEqual(len(ADULT_ANIMATION_STYLE_PROFILES), 6)
        self.assertEqual(
            adult_animation_profile_for_pilot("pilot_01"),
            ADULT_ANIMATION_FAMILY_STYLE_PROFILE,
        )
        first = select_adult_animation_layouts(
            ADULT_ANIMATION_FAMILY_STYLE_PROFILE, "reddit-source-a", 4,
        )
        repeat = select_adult_animation_layouts(
            ADULT_ANIMATION_FAMILY_STYLE_PROFILE, "reddit-source-a", 4,
        )
        second = select_adult_animation_layouts(
            ADULT_ANIMATION_FAMILY_STYLE_PROFILE, "reddit-source-b", 4,
        )
        self.assertEqual(first, repeat)
        self.assertEqual(len(first), len(set(first)))
        self.assertNotEqual(first, second)

    def test_caption_sidecar_normalizes_alignment_overlap_deterministically(self):
        text = "один два три четыре пять шесть семь восемь девять"
        words = []
        for index, word in enumerate(text.split()):
            start = index * 2.0
            end = start + 2.2
            words.append({
                "word": word,
                "start": start,
                "end": end,
                "timing_source": "ai33",
            })
        contract = build_cinematic_contract(
            narration_segments=[{
                "segment_id": "story_one",
                "kind": "story",
                "voice_role": "narrator",
                "text": text,
            }],
            segment_timings={
                "story_one": {
                    "duration_sec": 20.0,
                    "words": words,
                    "timing_source": "ai33",
                },
            },
            story_visuals={
                "story_one": [{
                    "local_path": "scene.png",
                    "sha256": "a" * 64,
                }],
            },
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=20.0,
        )
        cues = contract["caption_track"]["cues"]
        self.assertLessEqual(cues[0]["end_sec"], cues[1]["start_sec"])
        with tempfile.TemporaryDirectory() as temp:
            output = write_caption_srt(
                contract["caption_track"], Path(temp) / "captions.srt",
            )
            self.assertTrue(output.is_file())

    def test_long_service_bumper_fails_closed(self):
        with self.assertRaisesRegex(CinematicShotError, "short 17-second bumper"):
            build_cinematic_contract(
                narration_segments=[
                    {
                        "segment_id": "intro",
                        "kind": "intro",
                        "voice_role": "narrator",
                        "text": "Очень длинное вступление.",
                    },
                    {
                        "segment_id": "story_one",
                        "kind": "story",
                        "voice_role": "narrator",
                        "text": "История продолжается.",
                    },
                ],
                segment_timings={
                    "intro": {
                        "duration_sec": 18.0,
                        "words": [
                            {
                                "word": word,
                                "start": index * 5.0,
                                "end": (index + 1) * 5.0,
                                "timing_source": "ai33",
                            }
                            for index, word in enumerate(
                                "Очень длинное вступление.".split(),
                            )
                        ],
                        "timing_source": "ai33",
                    },
                    "story_one": {
                        "duration_sec": 20.0,
                        "words": [
                            {
                                "word": word,
                                "start": index * 6.0,
                                "end": (index + 1) * 6.0,
                                "timing_source": "ai33",
                            }
                            for index, word in enumerate(
                                "История продолжается.".split(),
                            )
                        ],
                        "timing_source": "ai33",
                    },
                },
                story_visuals={
                    "story_one": [{
                        "local_path": "scene.png",
                        "sha256": "a" * 64,
                    }],
                },
                story_metadata={"story_one": {"story_index": 1}},
                final_audio_duration_sec=38.0,
            )

    def test_service_bumper_accepts_provider_tail_and_post_pause(self):
        intro_text = "Короткое вступление."
        story_text = "История продолжается достаточно долго."
        contract = build_cinematic_contract(
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
                "intro": {
                    "duration_sec": 16.10551,
                    "words": [
                        {
                            "word": word,
                            "start": index * 7.0,
                            "end": (index + 1) * 7.0,
                            "timing_source": "ai33",
                        }
                        for index, word in enumerate(intro_text.split())
                    ],
                    "timing_source": "ai33",
                },
                "story_one": {
                    "duration_sec": 20.0,
                    "words": [
                        {
                            "word": word,
                            "start": index * 4.0,
                            "end": (index + 1) * 4.0,
                            "timing_source": "ai33",
                        }
                        for index, word in enumerate(story_text.split())
                    ],
                    "timing_source": "ai33",
                },
            },
            story_visuals={
                "story_one": [{
                    "local_path": "scene.png",
                    "sha256": "a" * 64,
                }],
            },
            story_metadata={"story_one": {"story_index": 1}},
            final_audio_duration_sec=36.10551,
        )

        self.assertAlmostEqual(contract["shots"][0]["duration_sec"], 16.106)

    def test_too_few_words_for_required_story_shots_fails_cleanly(self):
        with self.assertRaisesRegex(CinematicShotError, "fewer words"):
            build_cinematic_contract(
                narration_segments=[{
                    "segment_id": "story_one",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": "Два слова",
                }],
                segment_timings={
                    "story_one": {
                        "duration_sec": 100.0,
                        "words": [
                            {
                                "word": "Два",
                                "start": 0.0,
                                "end": 50.0,
                                "timing_source": "ai33",
                            },
                            {
                                "word": "слова",
                                "start": 50.0,
                                "end": 100.0,
                                "timing_source": "ai33",
                            },
                        ],
                        "timing_source": "ai33",
                    },
                },
                story_visuals={
                    "story_one": [{
                        "local_path": "scene.png",
                        "sha256": "a" * 64,
                    }],
                },
                story_metadata={"story_one": {"story_index": 1}},
                final_audio_duration_sec=100.0,
            )


if __name__ == "__main__":
    unittest.main()
