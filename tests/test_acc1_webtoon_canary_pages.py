import tempfile
import unittest
from pathlib import Path

from scripts.generate_acc1_webtoon_canary_pages import page_prompt, replace_scene_assets


class WebtoonCanaryPageTests(unittest.TestCase):
    def test_prompt_locks_light_three_panel_style(self):
        prompt = page_prompt({"narration_text": "Она закрыла дверь."}, 1)
        normalized = " ".join(prompt.split())
        self.assertIn("LIGHT GRAPHIC COMIC", normalized)
        self.assertIn("Exactly three unequal panels", normalized)
        self.assertIn("Never cinematic realism", normalized)
        self.assertIn("Она закрыла дверь", normalized)

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
