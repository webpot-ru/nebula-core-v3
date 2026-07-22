import tempfile
import unittest
from pathlib import Path

from acc1_editorial_motion import bind_payload
from scripts.render_acc1_webtoon_canary import (
    build_canary_storyboard,
    resolve_master_audio,
    resolve_storyboard,
    review_frame_times,
)


class WebtoonCanaryTests(unittest.TestCase):
    def test_resolves_single_nested_storyboard_and_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "artifact" / "build" / "recovered"
            nested.mkdir(parents=True)
            storyboard = nested / "storyboard-segmented.json"
            storyboard.write_text(
                '{"slides": [], "motion_plan": {}, "style_profile": "cinematic_ink_webtoon_v1"}',
                encoding="utf-8",
            )
            audio = nested / "tts" / "narration-master.mp3"
            audio.parent.mkdir()
            audio.write_bytes(b"audio")
            self.assertEqual(resolve_storyboard(Path(tmp)), storyboard)
            self.assertEqual(resolve_master_audio(Path(tmp)), audio)

    def test_rebases_four_scenes_and_preserves_zero_publication(self):
        scenes = []
        cues = []
        for index, module in enumerate(("living_photo_depth", "evidence_transform", "graphic_timeline", "nested_collage_zoom")):
            start = 10.0 + index * 4.0
            scenes.append({"presentation": "story", "start_sec": start, "end_sec": start + 4,
                           "duration_sec": 4.0, "motion": {"module": module}})
            cues.append({"cue_id": f"cue-{index}", "start_sec": start, "end_sec": start + 4,
                         "text": "тест", "text_sha256": "x"})
        plan = bind_payload({"scenes": scenes}, "motion_plan_sha256")
        captions = bind_payload({"cues": cues}, "caption_track_sha256")
        source = {"slides": scenes, "motion_plan": plan, "caption_track": captions,
                  "publication_authorized": False}
        canary, start, end = build_canary_storyboard(source)
        self.assertEqual((start, end), (10.0, 26.0))
        self.assertEqual(canary["timeline_duration_sec"], 16.0)
        self.assertEqual(canary["slides"][0]["start_sec"], 0.0)
        self.assertEqual(canary["slides"][-1]["end_sec"], 16.0)
        self.assertFalse(canary["publication_authorized"])
        self.assertEqual(review_frame_times(canary), [1.0, 5.0, 9.0, 13.0])

    def test_review_frames_stay_before_page_crossfade(self):
        storyboard = {"slides": [{"start_sec": 0.0, "duration_sec": 20.0}]}
        self.assertEqual(review_frame_times(storyboard), [5.0])
        with self.assertRaises(ValueError):
            review_frame_times(storyboard, progress=0.5)


if __name__ == "__main__":
    unittest.main()
