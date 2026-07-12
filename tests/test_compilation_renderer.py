import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from compilation_renderer import CompilationRenderError, preflight_storyboard, render_compilation


class CompilationRendererTests(unittest.TestCase):
    def _fixture(self, root: Path):
        image = root / "source.png"
        Image.new("RGB", (320, 180), "#552233").save(image)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        storyboard = {
            "format": "compilation_16x9", "resolution": [1920, 1080],
            "slides": [
                {"slide_id": "title", "kind": "title", "title": "Три страшные истории", "duration_sec": 0.5},
                {"slide_id": "image", "kind": "source_image", "duration_sec": 0.5, "visual": {"local_path": str(image), "sha256": digest, "caption": "Фото автора"}},
            ],
        }
        return storyboard, image

    def test_preflight_accepts_verified_local_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slides = preflight_storyboard(self._fixture(root)[0], root)
            self.assertEqual(Path(slides[1]["verified_image_path"]), (root / "source.png").resolve())

    def test_preflight_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, _ = self._fixture(root)
            storyboard["slides"][1]["visual"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(CompilationRenderError, "checksum mismatch"):
                preflight_storyboard(storyboard, root)

    def test_preflight_rejects_outside_path(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            storyboard, _ = self._fixture(root)
            image = Path(outside) / "outside.png"
            Image.new("RGB", (10, 10)).save(image)
            storyboard["slides"][1]["visual"].update(local_path=str(image), sha256=hashlib.sha256(image.read_bytes()).hexdigest())
            with self.assertRaisesRegex(CompilationRenderError, "under artifact_root"):
                preflight_storyboard(storyboard, root)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_renders_deterministic_16x9_mp4(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "result.mp4"
            report = render_compilation(self._fixture(root)[0], root, output)
            self.assertTrue(output.is_file())
            self.assertEqual(report["resolution"], [1920, 1080])
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output)], check=True, capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), "1920,1080")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_audio_merge_seam_adds_aac_track(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "narration.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=1", str(audio),
            ], check=True)
            output = root / "with-audio.mp4"
            report = render_compilation(self._fixture(root)[0], root, output, audio=audio)
            self.assertTrue(report["audio_merged"])
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(output),
            ], check=True, capture_output=True, text=True)
            self.assertEqual(probe.stdout.strip(), "aac")


if __name__ == "__main__":
    unittest.main()
