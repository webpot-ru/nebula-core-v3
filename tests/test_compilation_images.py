import tempfile
import unittest
from pathlib import Path

from compilation_images import generate_story_images, story_image_prompt


class CompilationImageTests(unittest.TestCase):
    def test_rules_and_clock_story_forbids_written_props(self):
        prompt = story_image_prompt({
            "title_ru": "Строгий список правил для смены в 3:15",
            "hook_ru": "Ночной уборщик", "editorial_review": {"verdict": "PASS"},
        })
        self.assertIn("Do not depict paper notes", prompt)
        self.assertIn("readable clock face", prompt)

    def test_generates_one_consistent_asset_per_story(self):
        compilation = {"stories": [{
            "title_ru": f"История {index}", "hook_ru": "Ночной коридор",
            "editorial_review": {"verdict": "PASS"},
            "source_snapshot": {"post_id": str(index)},
        } for index in range(1, 4)]}
        calls = []
        def generator(**kwargs):
            calls.append(kwargs)
            path = Path(kwargs["output_path"])
            path.write_bytes(b"image")
            return path
        with tempfile.TemporaryDirectory() as temp:
            assets = generate_story_images(compilation, Path(temp), generator=generator)
        self.assertEqual(len(assets), 3)
        self.assertTrue(all(call["model"] == "gpt-image-2" for call in calls))
        self.assertTrue(all("no text" in call["prompt"] for call in calls))

    def test_reuses_checksum_verified_matching_images(self):
        compilation = {"stories": [{
            "title_ru": f"История {index}", "hook_ru": "Ночной коридор",
            "editorial_review": {"verdict": "PASS"},
            "source_snapshot": {"post_id": str(index)},
        } for index in range(1, 4)]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def generator(**kwargs):
                path = Path(kwargs["output_path"])
                path.write_bytes(b"image")
                return path
            generated = generate_story_images(compilation, root, generator=generator)
            resume = {"stories": [{"source_snapshot": {"post_id": str(index)}, "generated_media": [generated[index - 1]]} for index in range(1, 4)]}
            reused_compilation = {"stories": [{
                "title_ru": f"История {index}", "hook_ru": "Ночной коридор",
                "editorial_review": {"verdict": "PASS"}, "source_snapshot": {"post_id": str(index)},
            } for index in range(1, 4)]}
            assets = generate_story_images(reused_compilation, root,
                generator=lambda **_: self.fail("matching images must not be regenerated"),
                resume_compilation=resume)
        self.assertEqual(len(assets), 3)

    def test_generates_four_distinct_source_backed_scene_visuals_per_story(self):
        compilation = {"stories": [{
            "title_ru": f"История {index}", "hook_ru": "Ночной коридор",
            "narration_ru": " ".join(
                f"Сцена {scene} содержит подтвержденное событие истории."
                for scene in range(1, 13)
            ),
            "editorial_review": {"verdict": "PASS"},
            "source_snapshot": {"post_id": str(index)},
        } for index in range(1, 4)]}
        calls = []

        def generator(**kwargs):
            calls.append(kwargs)
            path = Path(kwargs["output_path"])
            path.write_bytes(kwargs["prompt"].encode("utf-8"))
            return path

        with tempfile.TemporaryDirectory() as temp:
            assets = generate_story_images(
                compilation, Path(temp), generator=generator, images_per_story=4,
            )
        self.assertEqual(len(assets), 12)
        self.assertEqual(len(calls), 12)
        self.assertEqual({asset["scene_count"] for asset in assets}, {4})
        self.assertEqual({asset["scene_index"] for asset in assets}, {1, 2, 3, 4})
        self.assertEqual(len({call["prompt"] for call in calls[:4]}), 4)
        self.assertTrue(all("do not add a new plot event" in call["prompt"] for call in calls))


if __name__ == "__main__":
    unittest.main()
