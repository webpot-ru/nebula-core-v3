import tempfile
import unittest
from pathlib import Path

from compilation_images import generate_story_images


class CompilationImageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
