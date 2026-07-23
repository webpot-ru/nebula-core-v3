import tempfile
import unittest
from pathlib import Path

from scripts.generate_acc1_webtoon_canary_pages import page_prompt, replace_scene_assets
from acc1_visual_contract import FORMAT_VISUAL_SYSTEM_V3_STYLE_PROFILE


class WebtoonCanaryPageTests(unittest.TestCase):
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
