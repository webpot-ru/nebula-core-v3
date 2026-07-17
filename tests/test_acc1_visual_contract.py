import unittest
import tempfile
from pathlib import Path

from acc1_cinematic_shots import (
    CinematicShotError,
    build_cinematic_contract,
    write_caption_srt,
)
from acc1_visual_contract import (
    CINEMATIC_STORY_MODE,
    DEFAULT_VISUAL_MODE,
    REDDIT_PAGES_MODE,
    resolve_visual_mode,
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
        with self.assertRaisesRegex(CinematicShotError, "short 15-second bumper"):
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
                        "duration_sec": 16.0,
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
                final_audio_duration_sec=36.0,
            )

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
