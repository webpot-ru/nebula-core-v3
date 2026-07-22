import tempfile
import unittest
from pathlib import Path

from acc1_editorial_motion import bind_payload
from scripts.render_acc1_webtoon_canary import build_canary_storyboard, resolve_artifact_root


class WebtoonCanaryTests(unittest.TestCase):
    def test_resolves_single_nested_download_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "artifact" / "build" / "recovered"
            nested.mkdir(parents=True)
            (nested / "storyboard-single-audio.json").write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_artifact_root(Path(tmp)), nested)

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


if __name__ == "__main__":
    unittest.main()
