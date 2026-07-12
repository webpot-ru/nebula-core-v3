import tempfile
import unittest
from pathlib import Path

from compilation_storyboard import CompilationStoryboardError, build_storyboard


class CompilationStoryboardTests(unittest.TestCase):
    def test_includes_verified_local_source_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "photo.png"
            image.write_bytes(b"fixture")
            compilation = {"stories": [{"source_snapshot": {"title": "Story", "source_url": "https://reddit/x", "source_media": [{"download_status": "verified", "local_path": str(image), "sha256": "abc"}]}}]}
            storyboard = build_storyboard(compilation, root)
            self.assertTrue(any(slide["kind"] == "source_image" for slide in storyboard["slides"]))

    def test_rejects_image_outside_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            image = Path(outside) / "photo.png"
            image.write_bytes(b"fixture")
            compilation = {"stories": [{"source_snapshot": {"source_media": [{"download_status": "verified", "local_path": str(image)}]}}]}
            with self.assertRaises(CompilationStoryboardError):
                build_storyboard(compilation, Path(temp))


if __name__ == "__main__":
    unittest.main()
