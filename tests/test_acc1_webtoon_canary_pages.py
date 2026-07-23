import tempfile
import unittest
from pathlib import Path

from scripts.generate_acc1_webtoon_canary_pages import (
    build_panel_grammar_canary_storyboard,
    expand_four_scene_canary_to_five,
    page_prompt,
    replace_scene_assets,
    resolve_source_storyboard,
)
from acc1_visual_contract import FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE


class WebtoonCanaryPageTests(unittest.TestCase):
    def test_four_verified_beats_expand_to_five_without_changing_total_duration(self):
        slides = []
        for index, module in enumerate((
            "living_photo_depth",
            "evidence_transform",
            "memory_pullback",
            "dialogue_pressure",
        ), start=1):
            start = float(index - 1) * 4
            slides.append({
                "scene_id": f"scene-{index}",
                "presentation": "story",
                "start_sec": start,
                "end_sec": start + 4,
                "duration_sec": 4.0,
                "narration_text": "Она открыла письмо. И увидела подпись.",
                "motion": {"module": module},
            })
        source = {
            "style_profile": FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE,
            "slides": slides,
            "motion_plan": {"version": 1},
            "caption_track": {
                "version": 1,
                "cues": [{"start_sec": 0, "end_sec": 16, "text": "Она открыла письмо."}],
            },
        }
        four, _, _, strategy = build_panel_grammar_canary_storyboard(source, scene_count=5)
        self.assertEqual(strategy, "split_opening_beat")
        self.assertEqual(len(four["slides"]), 5)
        self.assertEqual(four["timeline_duration_sec"], 16.0)
        self.assertEqual(four["slides"][0]["narration_text"], "Она открыла письмо.")
        self.assertEqual(four["slides"][1]["narration_text"], "И увидела подпись.")
        self.assertEqual(len(expand_four_scene_canary_to_five({
            **four,
            "slides": slides,
            "timeline_duration_sec": 16.0,
        })["slides"]), 5)

    def test_selects_the_generated_v3_input_not_a_derived_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source" / "storyboard-generated.json"
            source.parent.mkdir()
            source.write_text(
                '{"style_profile":"acc1_format_visual_system_v3","slides":[],"motion_plan":{},"caption_track":{}}',
                encoding="utf-8",
            )
            (root / "derived" / "storyboard-canary.json").parent.mkdir()
            (root / "derived" / "storyboard-canary.json").write_text(
                '{"style_profile":"acc1_format_visual_system_v3","slides":[],"motion_plan":{},"caption_track":{}}',
                encoding="utf-8",
            )
            self.assertEqual(resolve_source_storyboard(root), source)

    def test_refuses_ambiguous_generated_v3_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in (1, 2):
                source = root / str(index) / "storyboard-generated.json"
                source.parent.mkdir()
                source.write_text(
                    '{"style_profile":"acc1_format_visual_system_v3","slides":[],"motion_plan":{},"caption_track":{}}',
                    encoding="utf-8",
                )
            with self.assertRaisesRegex(RuntimeError, "found 2"):
                resolve_source_storyboard(root)

    def test_prompt_locks_approved_v3_bundle_style(self):
        prompt = page_prompt({"narration_text": "Она закрыла дверь."}, 1)
        normalized = " ".join(prompt.split())
        self.assertIn("premium adult hand-drawn graphic-novel page", normalized)
        self.assertIn("BUNDLE grammar", normalized)
        self.assertIn("never photography", normalized)
        self.assertIn("never an orange-dominated universal palette", normalized)
        self.assertIn("Она закрыла дверь", normalized)
        self.assertIn("exactly one uninterrupted full-page hero image", normalized)

    def test_canary_prompt_uses_a_different_panel_count_for_each_meaningful_beat(self):
        prompts = [
            page_prompt({"narration_text": "Она закрыла дверь."}, index, 4)
            for index in range(1, 5)
        ]
        self.assertIn("exactly one uninterrupted full-page hero image", prompts[0])
        self.assertIn("exactly two unequal panels", prompts[1])
        self.assertIn("exactly four uneven panels", prompts[2])
        self.assertIn("exactly five asymmetrical panels", prompts[3])

    def test_five_page_canary_covers_each_approved_panel_count_once(self):
        prompts = [
            page_prompt({"narration_text": "Она закрыла дверь."}, index, 5)
            for index in range(1, 6)
        ]
        expected_phrases = (
            "exactly one uninterrupted full-page hero image",
            "exactly two unequal panels",
            "exactly three unequal panels",
            "exactly four uneven panels",
            "exactly five asymmetrical panels",
        )
        self.assertTrue(all(phrase in prompt for phrase, prompt in zip(expected_phrases, prompts)))

    def test_replaces_each_scene_with_one_unique_complete_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = []
            for index in range(2):
                page = root / f"page-{index}.png"
                page.write_bytes(f"page-{index}".encode())
                pages.append(page)
            storyboard = {"slides": [
                {"motion": {"module": "living_photo_depth"}},
                {"motion": {"module": "evidence_transform"}},
            ]}
            replaced = replace_scene_assets(storyboard, pages, root)
            self.assertEqual(len(replaced["slides"][0]["assets"]), 2)
            self.assertNotEqual(replaced["slides"][0]["assets"][0]["sha256"],
                                replaced["slides"][1]["assets"][0]["sha256"])
            self.assertEqual(replaced["slides"][0]["assets"][0]["local_path"], "page-0.png")
            self.assertEqual(replaced["style_profile"], FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE)
            self.assertEqual(replaced["slides"][0]["page_layout"], "bundle_story_opener")
            self.assertEqual(replaced["slides"][1]["page_layout"], "bundle_guided_page")
            self.assertEqual(replaced["slides"][0]["panel_count"], 1)
            self.assertEqual(replaced["slides"][1]["panel_count"], 5)
            self.assertEqual(replaced["slides"][0]["panel_grammar"], "bundle_hook")
            self.assertRegex(replaced["slides"][0]["asset_pack_sha256"], r"^[0-9a-f]{64}$")
