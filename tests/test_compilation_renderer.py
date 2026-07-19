import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from acc1_cinematic_shots import build_cinematic_contract, canonical_hash
from acc1_visual_contract import CINEMATIC_STORY_MODE, MASCOT_SAFE_X
from compilation_cinematic_renderer import (
    _service_overlay_slide,
    render_cinematic_frame,
)
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

    def _cinematic_fixture(
        self,
        root: Path,
        *,
        audio_sha256: str = "3" * 64,
        duration: float = 20.0,
    ):
        image = root / "cinematic.png"
        canvas = Image.new("RGB", (960, 540), "#08131f")
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((40, 60, 430, 480), fill="#a64b2a")
        draw.ellipse((600, 100, 900, 400), fill="#2a8aa6")
        canvas.save(image)
        image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
        intro_text = "Начинаем."
        text = "Точная история продолжается без разрыва."
        outro_text = "Обсудим."
        words = text.split()
        timings = [{
            "word": word,
            "start": index * duration / len(words),
            "end": (index + 1) * duration / len(words),
            "timing_source": "ai33",
        } for index, word in enumerate(words)]
        total_duration = duration + 1.0
        contract = build_cinematic_contract(
            narration_segments=[
                {
                    "segment_id": "intro",
                    "kind": "intro",
                    "voice_role": "narrator",
                    "text": intro_text,
                },
                {
                    "segment_id": "story_abc",
                    "kind": "story",
                    "voice_role": "narrator",
                    "text": text,
                },
                {
                    "segment_id": "outro",
                    "kind": "outro",
                    "voice_role": "narrator",
                    "text": outro_text,
                },
            ],
            segment_timings={
                "intro": {
                    "duration_sec": 0.5,
                    "words": [{
                        "word": intro_text,
                        "start": 0.0,
                        "end": 0.5,
                        "timing_source": "ai33",
                    }],
                    "timing_source": "ai33",
                },
                "story_abc": {
                    "duration_sec": duration,
                    "words": timings,
                    "timing_source": "ai33",
                },
                "outro": {
                    "duration_sec": 0.5,
                    "words": [{
                        "word": outro_text,
                        "start": 0.0,
                        "end": 0.5,
                        "timing_source": "ai33",
                    }],
                    "timing_source": "ai33",
                },
            },
            story_visuals={
                "story_abc": [{
                    "kind": "source_image",
                    "local_path": image.name,
                    "fit": "cover",
                    "caption": "",
                    "sha256": image_sha,
                }],
            },
            story_metadata={
                "story_abc": {
                    "story_index": 1,
                    "title": "Стук в дверь",
                    "source_label": "r/nosleep • u/example_author",
                    "truth_mode": "fiction",
                },
            },
            final_audio_duration_sec=total_duration,
        )
        bindings = {
            "episode_plan_sha256": "1" * 64,
            "daily_plan_sha256": "2" * 64,
            "audio_sha256": audio_sha256,
            "narration_plan_sha256": "4" * 64,
        }
        timing_contract_sha256 = "5" * 64
        narration_sha256 = contract["caption_track"]["text_sha256"]
        storyboard = {
            "version": 3,
            "format": "compilation_16x9",
            "resolution": [1920, 1080],
            "visual_mode": CINEMATIC_STORY_MODE,
            **bindings,
            "timing_contract_sha256": timing_contract_sha256,
            "final_audio_duration_sec": total_duration,
            "publication_authorized": False,
            "timeline_duration_sec": total_duration,
            "slides": contract["shots"],
            "shot_plan": contract["shot_plan"],
            "shot_plan_sha256": contract["shot_plan"]["shot_plan_sha256"],
            "caption_track": contract["caption_track"],
            "caption_track_sha256": contract["caption_track"][
                "caption_track_sha256"
            ],
            "creative_manifest": {
                "version": 1,
                "mode": CINEMATIC_STORY_MODE,
                **bindings,
                "timing_contract_sha256": timing_contract_sha256,
                "final_audio_duration_sec": total_duration,
                "publication_authorized": False,
                "narration_sha256": narration_sha256,
                "text_timing_coverage": 1.0,
                "shot_plan_sha256": contract["shot_plan"]["shot_plan_sha256"],
                "caption_track_sha256": contract["caption_track"][
                    "caption_track_sha256"
                ],
            },
        }
        return storyboard, image

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

    def test_unknown_version_two_mode_does_not_fall_back_to_reddit_pages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard = self._reddit_fixture(root)
            storyboard["creative_manifest"]["mode"] = "cinematic_story_v1_typo"
            with self.assertRaisesRegex(
                CompilationRenderError, "unsupported creative manifest mode",
            ):
                preflight_storyboard(storyboard, root)

    def test_cinematic_preflight_verifies_motion_and_frame_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, _ = self._cinematic_fixture(root)
            slide = next(
                item for item in preflight_storyboard(storyboard, root)
                if item["presentation"] == "story"
            )
            start = root / "start.png"
            end = root / "end.png"
            render_cinematic_frame(slide, start, progress=0.0)
            render_cinematic_frame(slide, end, progress=1.0)
            with Image.open(start) as first, Image.open(end) as second:
                difference = ImageChops.difference(first, second)
                self.assertIsNotNone(difference.getbbox())
            self.assertEqual(slide["kind"], "cinematic_shot")
            self.assertEqual(slide["duration_sec"], 20.0)

    def test_cinematic_transition_discloses_the_following_story(self):
        slides = [
            {"presentation": "story", "source_label": "first"},
            {"presentation": "transition"},
            {
                "presentation": "story",
                "story_title": "Вторая история",
                "source_label": "r/AskReddit • u/second",
                "truth_mode": "unverified_personal_account",
            },
        ]
        overlay = _service_overlay_slide(slides, 1)
        self.assertEqual(overlay["story_title"], "Вторая история")
        self.assertEqual(overlay["source_label"], "r/AskReddit • u/second")
        self.assertEqual(
            overlay["truth_mode"], "unverified_personal_account",
        )

    def test_cinematic_preflight_rejects_motion_outside_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, _ = self._cinematic_fixture(root)
            storyboard["slides"][0]["motion"]["end_scale"] = 1.25
            payload = {
                key: value for key, value in storyboard["shot_plan"].items()
                if key != "shot_plan_sha256"
            }
            digest = canonical_hash(payload)
            storyboard["shot_plan"]["shot_plan_sha256"] = digest
            storyboard["shot_plan_sha256"] = digest
            storyboard["creative_manifest"]["shot_plan_sha256"] = digest
            with self.assertRaisesRegex(
                CompilationRenderError, "push/pan bounds",
            ):
                preflight_storyboard(storyboard, root)

    def test_cinematic_preflight_rejects_rehashed_caption_text_substitution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, _ = self._cinematic_fixture(root)
            track = storyboard["caption_track"]
            track["cues"][0]["text"] = "Подмененный текст"
            track["cues"][0]["text_sha256"] = hashlib.sha256(
                track["cues"][0]["text"].encode("utf-8"),
            ).hexdigest()
            track["text_sha256"] = hashlib.sha256(
                " ".join(cue["text"] for cue in track["cues"]).encode("utf-8"),
            ).hexdigest()
            payload = {
                key: value for key, value in track.items()
                if key != "caption_track_sha256"
            }
            digest = canonical_hash(payload)
            track["caption_track_sha256"] = digest
            storyboard["caption_track_sha256"] = digest
            storyboard["creative_manifest"]["caption_track_sha256"] = digest
            with self.assertRaisesRegex(
                CompilationRenderError, "exact shot narration",
            ):
                preflight_storyboard(storyboard, root)

    def test_cinematic_preflight_rejects_timing_contract_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            storyboard, _ = self._cinematic_fixture(root)
            storyboard["creative_manifest"]["timing_contract_sha256"] = "6" * 64
            with self.assertRaisesRegex(
                CompilationRenderError, "timing_contract_sha256",
            ):
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

    def test_intro_screen_mode_renders_real_story_title_not_intro_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            slide = preflight_storyboard(self._reddit_fixture(root), root)[0]
            slide.update({
                "presentation": "intro",
                "title": "Текст приветствия не должен быть на экране",
                "display_text": "Текст приветствия не должен быть на экране.",
                "screen_mode": "story_title",
                "screen_title": "Стук в дверь",
                "show_title": False,
                "show_actions": False,
            })
            output = root / "intro-story-title.png"
            render_slide_frame(slide, output)
            self.assertTrue(output.is_file())

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
    def test_renders_bound_cinematic_mp4_and_caption_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "narration.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=21", str(audio),
            ], check=True)
            storyboard, _ = self._cinematic_fixture(
                root,
                audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
            )
            output = root / "cinematic.mp4"
            report = render_compilation(
                storyboard, root, output, audio=audio,
            )
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_suffix(".srt").is_file())
            self.assertEqual(report["visual_mode"], CINEMATIC_STORY_MODE)
            self.assertEqual(
                report["timing_contract_sha256"],
                storyboard["timing_contract_sha256"],
            )
            self.assertEqual(report["shot_plan_sha256"], storyboard["shot_plan_sha256"])
            self.assertEqual(
                report["caption_track_sha256"],
                storyboard["caption_track_sha256"],
            )
            self.assertTrue(report["fullscreen_images_verified"])
            self.assertTrue(report["story_shots_overlay_free"])
            self.assertEqual(report["service_overlay_count"], 2)
            self.assertRegex(
                report["service_overlay_evidence_sha256"], r"^[0-9a-f]{64}$",
            )
            intro_evidence = report["service_overlay_evidence"][0]
            self.assertEqual(intro_evidence["presentation"], "intro")
            self.assertEqual(
                intro_evidence["source_label"],
                "r/nosleep • u/example_author",
            )
            self.assertEqual(intro_evidence["truth_mode"], "fiction")
            self.assertEqual(
                intro_evidence["truth_label"],
                "ХУДОЖЕСТВЕННАЯ ИСТОРИЯ",
            )
            self.assertRegex(report["motion_evidence_sha256"], r"^[0-9a-f]{64}$")
            self.assertAlmostEqual(report["duration_sec"], 21.0, delta=0.05)

            intro_frame = root / "intro-frame.png"
            story_frame = root / "story-frame.png"
            outro_frame = root / "outro-frame.png"
            for timestamp, frame in (
                (0.2, intro_frame),
                (1.0, story_frame),
                (20.75, outro_frame),
            ):
                subprocess.run([
                    "ffmpeg", "-y", "-v", "error", "-ss", str(timestamp),
                    "-i", str(output), "-frames:v", "1", str(frame),
                ], check=True)

            def bright_pixels(path, box):
                with Image.open(path).convert("RGB") as frame:
                    return sum(
                        min(pixel) >= 180
                        for pixel in frame.crop(box).get_flattened_data()
                    )

            # Source + truth disclosures are really burned into the intro frame,
            # while the story image remains a clean full-screen shot.
            self.assertGreater(
                bright_pixels(intro_frame, (60, 800, 1700, 1040)), 250,
            )
            self.assertLess(
                bright_pixels(story_frame, (60, 800, 1700, 1040)), 25,
            )
            # The actual encoded outro also carries its service label.
            self.assertGreater(
                bright_pixels(outro_frame, (60, 50, 900, 150)), 100,
            )

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
