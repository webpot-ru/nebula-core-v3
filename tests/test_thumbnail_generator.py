import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

import thumbnail_generator


class ThumbnailGeneratorTests(unittest.TestCase):
    def _metadata(self, root: Path) -> Path:
        path = root / "metadata.json"
        path.write_text(json.dumps({
            "thumbnail_prompt": "A dark hallway with a distant open door",
            "thumbnail_text": "ОН БЫЛ ЗА ДВЕРЬЮ",
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def test_local_overlay_is_1280x720_and_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.png"
            output = root / "thumbnail.png"
            report = root / "thumbnail-report.json"
            Image.new("RGB", (900, 900), "#527a91").save(base)
            with patch.object(thumbnail_generator, "call_image_generation") as provider:
                result = thumbnail_generator.main([
                    "--metadata", str(self._metadata(root)),
                    "--base-image", str(base), "--output", str(output), "--report", str(report),
                ])
            self.assertEqual(result, 0)
            provider.assert_not_called()
            with Image.open(output) as image:
                self.assertEqual(image.size, (1280, 720))
                self.assertIsNotNone(image.getbbox())
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["dimensions"], [1280, 720])
            self.assertEqual(payload["mode"], "local-overlay")
            self.assertFalse(payload["provider_called"])
            self.assertEqual(payload["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_overlay_is_deterministic_and_changes_base_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.png"
            first, second = root / "first.png", root / "second.png"
            Image.new("RGB", (1280, 720), "#8090a0").save(base)
            thumbnail_generator.overlay_thumbnail_text(base, first, "ЭТО БЫЛ НЕ СОСЕД")
            thumbnail_generator.overlay_thumbnail_text(base, second, "ЭТО БЫЛ НЕ СОСЕД")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with Image.open(base) as original, Image.open(first) as composed:
                self.assertIsNotNone(ImageChops.difference(original.convert("RGB"), composed.convert("RGB")).getbbox())

    def test_dry_run_does_not_call_provider_or_write_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "thumbnail.png"
            report = root / "thumbnail-report.json"
            with patch.object(thumbnail_generator, "call_image_generation") as provider:
                result = thumbnail_generator.main([
                    "--metadata", str(self._metadata(root)),
                    "--output", str(output), "--report", str(report), "--dry-run",
                ])
            self.assertEqual(result, 0)
            provider.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
