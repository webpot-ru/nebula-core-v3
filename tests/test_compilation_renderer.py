import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from acc1_visual_contract import MASCOT_SAFE_X
from compilation_renderer import (
    CompilationRenderError,
    _font,
    _wrap_pixels,
    _compact_metric,
    preflight_storyboard,
    render_compilation,
    render_slide_frame,
    validate_compilation_text_layout,
)


class CompilationRendererTests(unittest.TestCase):
    @staticmethod
    def _complete_compilation():
        disclosure = "Это художественная история с Reddit."
        return {
            "title_ru": "Истории с Reddit",
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Сегодня читаем законченную историю. {disclosure}",
            "outro_ru": "Обсудим эту историю в комментариях.",
            "stories": [{
                "title_ru": "Сосед постучал ночью",
                "narration_ru": (
                    "Я проснулся от тихого стука в дверь. За дверью никого не было. "
                    "Утром сосед признался, что тоже слышал этот стук."
                ),
                "source_snapshot": {
                    "post_id": "abc", "truth_mode": "fiction",
                    "title": "A knock", "subreddit": "nosleep",
                    "author": "example_author", "score": 12400,
                    "num_comments": 428,
                },
            }],
        }

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

    def _reddit_fixture(
        self, root: Path, *, background: Path | None = None,
        audio_sha256: str = "3" * 64,
    ):
        text = "Ночью кто-то постучал в дверь."
        storyboard = {
            "version": 2,
            "format": "compilation_16x9",
            "resolution": [1920, 1080],
            "episode_plan_sha256": "1" * 64,
            "daily_plan_sha256": "2" * 64,
            "audio_sha256": audio_sha256,
            "narration_plan_sha256": "4" * 64,
            "publication_authorized": False,
            "slides": [{
                "slide_id": "story-01-page-001-step-01",
                "scene_id": "story-01-beat-001",
                "segment_id": "story-01",
                "kind": "reddit_page",
                "title": "Стук в дверь",
                "show_title": True,
                "show_actions": True,
                "presentation": "story",
                "voice_role": "narrator",
                "subreddit": "r/nosleep",
                "source_author": "u/example_author",
                "source_score": 12400,
                "source_comment_count": 428,
                "display_text": text,
                "narration_text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "duration_sec": 0.5,
                "start_sec": 0.0,
                "end_sec": 0.5,
            }],
            "creative_manifest": {
                "mode": "reddit_pages", "text_timing_coverage": 1.0,
                "episode_plan_sha256": "1" * 64,
                "daily_plan_sha256": "2" * 64,
                "audio_sha256": audio_sha256,
                "narration_plan_sha256": "4" * 64,
                "publication_authorized": False,
            },
        }
        if background:
            storyboard["background_video"] = {
                "kind": "background_video", "local_path": str(background),
                "sha256": hashlib.sha256(background.read_bytes()).hexdigest(),
                "loop": True, "audio_policy": "discard",
            }
        return storyboard

    def test_preflight_accepts_verified_local_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slides = preflight_storyboard(self._fixture(root)[0], root)
            self.assertEqual(Path(slides[1]["verified_image_path"]), (root / "source.png").resolve())

    def test_preflight_resolves_artifact_relative_image_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, image = self._fixture(root)
            storyboard["slides"][1]["visual"]["local_path"] = image.relative_to(root).as_posix()
            slides = preflight_storyboard(storyboard, root)
            self.assertEqual(
                Path(slides[1]["verified_image_path"]),
                image.resolve(),
            )

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

    def test_preflight_rejects_reddit_page_timing_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._reddit_fixture(root)
            second = dict(storyboard["slides"][0])
            second.update(slide_id="second", start_sec=1.0, end_sec=1.5)
            storyboard["slides"].append(second)
            with self.assertRaisesRegex(CompilationRenderError, "timing gap"):
                preflight_storyboard(storyboard, root)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_version_two_render_rejects_audio_not_bound_to_storyboard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "narration.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=1", str(audio),
            ], check=True)
            storyboard = self._reddit_fixture(root, audio_sha256="0" * 64)
            with self.assertRaisesRegex(CompilationRenderError, "audio checksum"):
                render_compilation(storyboard, root, root / "must-not-exist.mp4", audio=audio)

    def test_actions_appear_only_when_page_is_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slide = preflight_storyboard(self._reddit_fixture(root), root)[0]
            without_actions = root / "without-actions.png"
            with_actions = root / "with-actions.png"
            slide["show_actions"] = False
            render_slide_frame(slide, without_actions)
            slide["show_actions"] = True
            render_slide_frame(slide, with_actions)
            with Image.open(without_actions) as first, Image.open(with_actions) as second:
                action_difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
                self.assertIsNotNone(action_difference.getbbox())

    def test_reddit_metrics_use_english_compact_notation_without_fake_values(self):
        self.assertEqual(_compact_metric(12400, "Vote"), "12.4K")
        self.assertEqual(_compact_metric(428, "Comments"), "428")
        self.assertEqual(_compact_metric(None, "Vote"), "Vote")
        self.assertEqual(_compact_metric(-1, "Comments"), "Comments")

    def test_max_density_cyrillic_page_fits_without_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._reddit_fixture(root)
            text = " ".join(["неожиданно"] * 27)
            slide = storyboard["slides"][0]
            slide.update(
                display_text=text,
                narration_text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                show_actions=True,
            )
            checked = preflight_storyboard(storyboard, root)[0]
            render_slide_frame(checked, root / "dense-page.png")
            self.assertTrue((root / "dense-page.png").is_file())

    def test_overwide_word_fails_in_first_middle_and_last_position(self):
        draw = ImageDraw.Draw(Image.new("L", (1, 1), 0))
        overwide = "я" * 200
        for text in (overwide, f"коротко {overwide} потом", f"коротко {overwide}"):
            with self.subTest(text_position=text[:12]):
                with self.assertRaisesRegex(CompilationRenderError, "word wider"):
                    _wrap_pixels(draw, text, _font(48), 948)

    def test_pre_spend_layout_rejects_translated_title_over_three_lines(self):
        compilation = self._complete_compilation()
        compilation["stories"][0]["title_ru"] = " ".join(
            ["неожиданное"] * 80
        )
        with self.assertRaisesRegex(CompilationRenderError, "three lines"):
            validate_compilation_text_layout(compilation)

    def test_pre_spend_layout_checks_cumulative_pages_and_final_actions(self):
        compilation = self._complete_compilation()
        clauses = [
            f"Сначала герой заметил деталь номер {index}, а затем проверил её спокойно."
            for index in range(1, 24)
        ]
        compilation["stories"][0]["narration_ru"] = " ".join(clauses)
        report = validate_compilation_text_layout(compilation)
        self.assertEqual(report["status"], "PASS")
        self.assertGreater(report["page_count"], 3)
        self.assertGreater(report["state_count"], report["page_count"])
        self.assertRegex(report["page_states_sha256"], r"^[0-9a-f]{64}$")

    def test_story_image_and_readability_shade_do_not_touch_mascot_safe_region(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "story.png"
            Image.new("RGB", (1536, 864), "#ffffff").save(image)
            storyboard = self._reddit_fixture(root)
            storyboard["slides"][0]["visual"] = {
                "local_path": str(image),
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }
            slide = preflight_storyboard(storyboard, root)[0]
            output = root / "mascot-safe-overlay.png"
            render_slide_frame(slide, output, transparent=True)
            with Image.open(output) as frame:
                safe_region = frame.crop((MASCOT_SAFE_X, 0, frame.width, frame.height))
                self.assertIsNone(safe_region.getbbox())

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

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
    def test_renders_reddit_page_over_verified_looping_background(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            background = root / "loop.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=0x245070:s=640x360:d=0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(background),
            ], check=True)
            output = root / "reddit-page.mp4"
            audio = root / "narration.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=1", str(audio),
            ], check=True)
            storyboard = self._reddit_fixture(
                root,
                background=background,
                audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
            )
            report = render_compilation(storyboard, root, output, audio=audio)
            self.assertTrue(output.is_file())
            self.assertTrue(report["background_video_used"])
            self.assertEqual(report["reddit_page_count"], 1)
            self.assertEqual(report["text_timing_coverage"], 1.0)
            self.assertEqual(report["episode_plan_sha256"], "1" * 64)
            self.assertEqual(report["daily_plan_sha256"], "2" * 64)
            self.assertEqual(report["audio_sha256"], hashlib.sha256(audio.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
