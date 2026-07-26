import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from acc1_cinematic_shots import verify_bound_payload, write_caption_srt
from acc1_narration_profiles import STRANGE_DARK_UNEXPLAINED_PROFILE_ID
from acc1_visual_contract import CINEMATIC_STORY_MODE
from compilation_audio_mix import build_pause_map
from compilation_storyboard import (
    CompilationStoryboardError,
    _timed_chunks,
    _verified_editorial_assets,
    build_storyboard,
    narration_sha256,
)
from compilation_tts_runner import (
    _canonical_hash,
    _new_state,
    _state_timing_contract,
    build_tts_chunks,
)


class CompilationStoryboardTests(unittest.TestCase):
    @staticmethod
    def _complete_compilation():
        disclosure = "Это художественная история с Reddit."
        return {
            "episode_plan_sha256": "1" * 64,
            "daily_plan_sha256": "2" * 64,
            "publication_authorized": False,
            "title_ru": "Истории с Reddit",
            "truth_disclosure_ru": disclosure,
            "intro_ru": f"Сегодня читаем одну законченную историю. {disclosure}",
            "mid_story_cta_ru": "Верите, что этому есть объяснение? Напишите свою версию",
            "outro_ru": "Как бы вы поступили? Напишите в комментариях.",
            "stories": [{
                "title_ru": "Сосед постучал ночью",
                "narration_ru": (
                    "Я проснулся от тихого стука в дверь. За дверью никого не было. "
                    "Утром сосед признался, что тоже слышал этот стук. "
                    "Мы проверили камеру и увидели пустой коридор."
                ),
                "source_snapshot": {
                    "post_id": "abc", "truth_mode": "fiction",
                    "title": "A knock", "subreddit": "nosleep", "author": "example_author",
                    "score": 12400, "num_comments": 428, "source_media": [],
                },
            }],
        }

    @staticmethod
    def _tts_state(compilation):
        bindings = {
            "episode_plan_sha256": compilation["episode_plan_sha256"],
            "daily_plan_sha256": compilation["daily_plan_sha256"],
        }
        chunks = build_tts_chunks(compilation, voice_id="narrator")
        state = _new_state(chunks, bindings)
        raw_duration = 0.0
        for item in state["chunks"]:
            words = item["text"].split()
            duration = len(words) * 0.75
            timings = [
                {
                    "word": word,
                    "start": round(index * 0.75, 3),
                    "end": round((index + 1) * 0.75, 3),
                    "timing_source": "estimated_from_audio_duration",
                }
                for index, word in enumerate(words)
            ]
            item.update({
                "status": "COMPLETE",
                "audio_sha256": hashlib.sha256(item["chunk_id"].encode()).hexdigest(),
                "audio_duration_sec": duration,
                "timing_source": "estimated_from_audio_duration",
                "word_timings": timings,
                "word_timings_sha256": _canonical_hash(timings),
            })
            raw_duration += duration
        state.update({
            "status": "COMPLETE",
            "final_audio_sha256": "3" * 64,
            "timing_contract_version": 1,
            "final_audio_duration_sec": raw_duration,
            "raw_chunk_duration_sec": raw_duration,
            "timeline_scale": 1.0,
        })
        state["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(state))
        return state

    @classmethod
    def _profiled_tts_state(cls, compilation):
        compilation["pillar"] = "strange_dark_unexplained"
        compilation["narration_profile_id"] = (
            STRANGE_DARK_UNEXPLAINED_PROFILE_ID
        )
        bindings = {
            "episode_plan_sha256": compilation["episode_plan_sha256"],
            "daily_plan_sha256": compilation["daily_plan_sha256"],
        }
        chunks = build_tts_chunks(
            compilation,
            voice_id="narrator",
            narration_profile_id=STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
        )
        state = _new_state(chunks, bindings)
        raw_duration = 0.0
        for item in state["chunks"]:
            words = item["text"].split()
            duration = len(words) * 0.75
            timings = [{
                "word": word,
                "start": round(index * 0.75, 3),
                "end": round((index + 1) * 0.75, 3),
                "timing_source": "estimated_from_audio_duration",
            } for index, word in enumerate(words)]
            item.update({
                "status": "COMPLETE",
                "audio_path": f"tts/{item['chunk_id']}.wav",
                "audio_sha256": hashlib.sha256(item["chunk_id"].encode()).hexdigest(),
                "audio_duration_sec": duration,
                "timing_source": "estimated_from_audio_duration",
                "word_timings": timings,
                "word_timings_sha256": _canonical_hash(timings),
            })
            raw_duration += duration
        state.update({
            "status": "COMPLETE",
            "final_audio_sha256": "3" * 64,
            "timing_contract_version": 1,
            "final_audio_duration_sec": raw_duration,
            "raw_chunk_duration_sec": raw_duration,
            "timeline_scale": 1.0,
        })
        state["timing_contract_sha256"] = _canonical_hash(
            _state_timing_contract(state),
        )
        return state

    def test_includes_verified_local_source_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "photo.png"
            image.write_bytes(b"fixture")
            compilation = {"stories": [{"source_snapshot": {"title": "Story", "source_url": "https://reddit/x", "source_media": [{"download_status": "verified", "local_path": str(image), "sha256": "abc"}]}}]}
            storyboard = build_storyboard(compilation, root)
            image_slide = next(slide for slide in storyboard["slides"] if slide["kind"] == "source_image")
            self.assertEqual(image_slide["visual"]["local_path"], "photo.png")

    def test_rejects_image_outside_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            image = Path(outside) / "photo.png"
            image.write_bytes(b"fixture")
            compilation = {"stories": [{"source_snapshot": {"source_media": [{"download_status": "verified", "local_path": str(image)}]}}]}
            with self.assertRaises(CompilationStoryboardError):
                build_storyboard(compilation, Path(temp))

    def test_builds_cumulative_timed_reddit_pages_with_exact_text_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            compilation = self._complete_compilation()
            storyboard = build_storyboard(
                compilation, Path(temp), tts_state=self._tts_state(compilation),
            )
        self.assertEqual(storyboard["version"], 2)
        self.assertTrue(all(slide["kind"] == "reddit_page" for slide in storyboard["slides"]))
        self.assertEqual(storyboard["episode_plan_sha256"], "1" * 64)
        self.assertEqual(storyboard["daily_plan_sha256"], "2" * 64)
        self.assertEqual(storyboard["audio_sha256"], "3" * 64)
        self.assertRegex(storyboard["narration_plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(storyboard["publication_authorized"])
        self.assertEqual(
            {slide["voice_role"] for slide in storyboard["slides"]}, {"narrator"},
        )
        self.assertEqual(storyboard["creative_manifest"]["narration_sha256"], narration_sha256(compilation))
        self.assertEqual(storyboard["creative_manifest"]["text_timing_coverage"], 1.0)
        for previous, current in zip(storyboard["slides"], storyboard["slides"][1:]):
            self.assertAlmostEqual(previous["end_sec"], current["start_sec"], places=3)
        story_pages = [slide for slide in storyboard["slides"] if slide["segment_id"] == "story_abc"]
        self.assertGreaterEqual(len(story_pages), 2)
        same_page = [slide for slide in story_pages if slide["page_index"] == story_pages[0]["page_index"]]
        if len(same_page) > 1:
            self.assertTrue(same_page[1]["display_text"].startswith(same_page[0]["display_text"]))
        self.assertTrue(story_pages[-1]["show_actions"])
        cta_pages = [slide for slide in story_pages if slide.get("mid_story_cta")]
        self.assertEqual(len(cta_pages), 1)
        self.assertEqual(
            cta_pages[0]["mid_story_cta"]["placement"], "story_midpoint",
        )
        self.assertEqual(storyboard["creative_manifest"]["mid_story_cta_count"], 1)
        self.assertGreaterEqual(story_pages[-1]["duration_sec"], 0.5)
        self.assertFalse(any(slide["show_actions"] for slide in story_pages[:-1]))
        self.assertFalse(any(
            slide["show_actions"] for slide in storyboard["slides"]
            if not slide["segment_id"].startswith("story_")
        ))
        self.assertEqual({slide["subreddit"] for slide in story_pages}, {"r/nosleep"})
        self.assertEqual({slide["source_author"] for slide in story_pages}, {"u/example_author"})
        self.assertEqual({slide["source_score"] for slide in story_pages}, {12400})
        self.assertEqual({slide["source_comment_count"] for slide in story_pages}, {428})
        self.assertEqual(
            {slide["presentation"] for slide in storyboard["slides"] if slide["segment_id"] == "intro"},
            {"intro"},
        )
        self.assertEqual(
            {slide["presentation"] for slide in storyboard["slides"] if slide["segment_id"] == "outro"},
            {"outro"},
        )
        intro_slides = [slide for slide in storyboard["slides"] if slide["segment_id"] == "intro"]
        self.assertTrue(all(slide["screen_mode"] == "story_title" for slide in intro_slides))
        self.assertTrue(all(slide["screen_title"] == "Сосед постучал ночью" for slide in intro_slides))
        self.assertTrue(all(not slide["show_title"] for slide in story_pages))

    def test_brand_sting_is_checksum_bound_after_cold_open(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sting = root / "brand-sting.mp4"
            sting.write_bytes(b"local deterministic sting fixture")
            compilation = self._complete_compilation()
            compilation["intro_contract"] = {
                "cold_open": {
                    "text": "Сегодня читаем одну законченную историю.",
                    "source_id": "abc",
                    "source_quote": "A knock",
                },
            }
            compilation["brand_sting"] = {
                "local_path": sting.name,
                "sha256": hashlib.sha256(sting.read_bytes()).hexdigest(),
                "duration_sec": 1.5,
            }
            storyboard = build_storyboard(
                compilation, root, tts_state=self._tts_state(compilation),
            )
        contract = storyboard["brand_sting"]
        self.assertEqual(contract["placement"], "after_cold_open")
        self.assertEqual(contract["audio_policy"], "discard")
        self.assertEqual(contract["duration_sec"], 1.5)
        self.assertGreater(contract["start_sec"], 0)
        self.assertEqual(
            storyboard["creative_manifest"]["brand_sting"]["sha256"],
            contract["sha256"],
        )

    def test_brand_cta_and_outro_are_checksum_bound_to_timeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cta = root / "brand-cta.webm"
            outro = root / "brand-outro.mp4"
            cta.write_bytes(b"local transparent CTA fixture")
            outro.write_bytes(b"local outro fixture")
            compilation = self._complete_compilation()
            compilation["brand_cta"] = {
                "local_path": cta.name,
                "sha256": hashlib.sha256(cta.read_bytes()).hexdigest(),
                "duration_sec": 2.0,
            }
            compilation["brand_outro"] = {
                "local_path": outro.name,
                "sha256": hashlib.sha256(outro.read_bytes()).hexdigest(),
                "duration_sec": 6.0,
            }
            storyboard = build_storyboard(
                compilation, root, tts_state=self._tts_state(compilation),
            )

        cta_contract = storyboard["brand_cta"]
        outro_contract = storyboard["brand_outro"]
        first_story = [
            slide for slide in storyboard["slides"]
            if slide["segment_id"] == "story_abc"
        ]
        timeline_end = max(slide["end_sec"] for slide in storyboard["slides"])
        self.assertEqual(cta_contract["placement"], "first_story_midpoint")
        self.assertGreaterEqual(cta_contract["start_sec"], first_story[0]["start_sec"])
        self.assertLessEqual(
            cta_contract["start_sec"] + cta_contract["duration_sec"],
            first_story[-1]["end_sec"],
        )
        self.assertEqual(outro_contract["placement"], "timeline_end")
        self.assertAlmostEqual(
            outro_contract["start_sec"] + outro_contract["duration_sec"],
            timeline_end,
            places=3,
        )
        self.assertEqual(cta_contract["audio_policy"], "discard")
        self.assertEqual(outro_contract["audio_policy"], "discard")
        self.assertEqual(
            storyboard["creative_manifest"]["brand_cta"]["sha256"],
            cta_contract["sha256"],
        )

    def test_cinematic_storyboard_is_full_screen_continuous_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "scene.png"
            Image.new("RGB", (1536, 864), "#314159").save(image)
            compilation = self._complete_compilation()
            compilation["visual_mode"] = CINEMATIC_STORY_MODE
            compilation["stories"][0]["generated_media"] = [{
                "download_status": "verified",
                "local_path": "scene.png",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }]
            state = self._tts_state(compilation)
            first = build_storyboard(compilation, root, tts_state=state)
            second = build_storyboard(compilation, root, tts_state=state)
            caption_path = write_caption_srt(
                first["caption_track"], root / "captions.srt",
            )

        self.assertEqual(first["visual_mode"], CINEMATIC_STORY_MODE)
        self.assertEqual(first["version"], 3)
        self.assertTrue(all(
            slide["kind"] == "cinematic_shot" for slide in first["slides"]
        ))
        self.assertTrue(all(
            slide["visual"]["fit"] == "cover" for slide in first["slides"]
        ))
        story_shots = [
            slide for slide in first["slides"]
            if slide["presentation"] == "story"
        ]
        self.assertTrue(all(
            20 <= slide["duration_sec"] <= 45 for slide in story_shots
        ))
        for previous, current in zip(first["slides"], first["slides"][1:]):
            self.assertAlmostEqual(previous["end_sec"], current["start_sec"], places=3)
        self.assertTrue(verify_bound_payload(first["shot_plan"], "shot_plan_sha256"))
        self.assertTrue(verify_bound_payload(
            first["caption_track"], "caption_track_sha256",
        ))
        self.assertEqual(first["shot_plan_sha256"], second["shot_plan_sha256"])
        self.assertEqual(
            first["caption_track_sha256"], second["caption_track_sha256"],
        )
        self.assertTrue(caption_path.name.endswith(".srt"))

    def test_cinematic_storyboard_rejects_unverified_image_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "scene.png"
            Image.new("RGB", (1536, 864), "#314159").save(image)
            compilation = self._complete_compilation()
            compilation["stories"][0]["generated_media"] = [{
                "download_status": "verified",
                "local_path": "scene.png",
                "sha256": "0" * 64,
            }]
            with self.assertRaisesRegex(
                CompilationStoryboardError, "verified file checksum",
            ):
                build_storyboard(
                    compilation,
                    root,
                    visual_mode=CINEMATIC_STORY_MODE,
                    tts_state=self._tts_state(compilation),
                )

    def test_verified_editorial_assets_preserve_v3_panel_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "scene.png"
            Image.new("RGB", (1536, 864), "#314159").save(image)
            assets = _verified_editorial_assets({
                "generated_media": [{
                    "download_status": "verified",
                    "local_path": "scene.png",
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                    "asset_family_id": "story-01-pack-001",
                    "layer_role": "hero_plate",
                    "motion_module": "living_photo_depth",
                    "story_family": "relationships",
                    "page_layout": "bundle_story_opener",
                    "panel_grammar": "hero_single",
                    "panel_count": 1,
                    "panel_beat_role": "hero_single",
                }],
            }, root)

        self.assertEqual(assets[0]["story_family"], "relationships")
        self.assertEqual(assets[0]["page_layout"], "bundle_story_opener")
        self.assertEqual(assets[0]["panel_grammar"], "hero_single")
        self.assertEqual(assets[0]["panel_count"], 1)
        self.assertEqual(assets[0]["panel_beat_role"], "hero_single")

    def test_cinematic_storyboard_binds_exact_pause_and_mix_timeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "scene.png"
            Image.new("RGB", (1536, 864), "#314159").save(image)
            compilation = self._complete_compilation()
            compilation["visual_mode"] = CINEMATIC_STORY_MODE
            compilation["stories"][0]["generated_media"] = [{
                "download_status": "verified",
                "local_path": "scene.png",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            }]
            state = self._profiled_tts_state(compilation)
            pause_map = build_pause_map(state)
            mix_report = {
                "version": 1,
                "status": "PASS",
                "episode_plan_sha256": state["episode_plan_sha256"],
                "daily_plan_sha256": state["daily_plan_sha256"],
                "narration_plan_sha256": state["narration_plan_sha256"],
                "timing_contract_sha256": state["timing_contract_sha256"],
                "narration_profile_id": state["narration_profile_id"],
                "narration_profile_sha256": state["narration_profile_sha256"],
                "pause_map_sha256": pause_map["pause_map_sha256"],
                "output_sha256": "4" * 64,
                "output_duration_sec": pause_map["timeline_duration_sec"],
                "expected_timeline_duration_sec": pause_map[
                    "timeline_duration_sec"
                ],
                "duration_tolerance_sec": 0.25,
                "publication_authorized": False,
            }
            mix_report["audio_mix_report_sha256"] = _canonical_hash(mix_report)
            storyboard = build_storyboard(
                compilation,
                root,
                tts_state=state,
                pause_map=pause_map,
                audio_mix_report=mix_report,
            )

        self.assertEqual(storyboard["audio_sha256"], "4" * 64)
        self.assertEqual(
            storyboard["timeline_duration_sec"],
            round(pause_map["timeline_duration_sec"], 3),
        )
        self.assertEqual(
            storyboard["pause_map_sha256"], pause_map["pause_map_sha256"],
        )
        self.assertEqual(
            storyboard["audio_mix_report_sha256"],
            mix_report["audio_mix_report_sha256"],
        )
        self.assertEqual(
            storyboard["slides"][-1]["end_sec"],
            round(pause_map["timeline_duration_sec"], 3),
        )

        tampered = dict(mix_report, output_sha256="5" * 64)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(
                CompilationStoryboardError, "audio mix report checksum",
            ):
                build_storyboard(
                    compilation,
                    Path(temp),
                    tts_state=state,
                    pause_map=pause_map,
                    audio_mix_report=tampered,
                )

    def test_page_boundaries_follow_bound_ai33_alignment_pause(self):
        compilation = self._complete_compilation()
        state = self._tts_state(compilation)
        story_item = next(
            item for item in state["chunks"] if item["logical_segment_id"] == "story_abc"
        )
        page_chunks = _timed_chunks(story_item["text"])
        self.assertGreaterEqual(len(page_chunks), 2)
        first_page_words = len(page_chunks[0][1].split())
        tokens = story_item["text"].split()
        duration = float(story_item["audio_duration_sec"])
        remaining = len(tokens) - first_page_words
        timings = []
        for index, word in enumerate(tokens):
            if index < first_page_words:
                start = index / first_page_words
                end = (index + 1) / first_page_words
            else:
                relative = index - first_page_words
                start = 8.0 + (duration - 8.0) * relative / remaining
                end = 8.0 + (duration - 8.0) * (relative + 1) / remaining
            timings.append({
                "word": word,
                "start": round(start, 3),
                "end": round(end, 3),
                "timing_source": "ai33",
            })
        story_item["timing_source"] = "ai33"
        story_item["word_timings"] = timings
        story_item["word_timings_sha256"] = _canonical_hash(timings)
        state["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(state))

        with tempfile.TemporaryDirectory() as temp:
            storyboard = build_storyboard(compilation, Path(temp), tts_state=state)

        story_slides = [
            slide for slide in storyboard["slides"] if slide["segment_id"] == "story_abc"
        ]
        self.assertAlmostEqual(story_slides[0]["duration_sec"], 7.92, places=3)
        self.assertIn("ai33", storyboard["creative_manifest"]["timing_sources"])
        self.assertEqual(storyboard["creative_manifest"]["audio_timing_coverage"], 1.0)

    def test_tampered_word_timing_is_rejected_before_storyboard(self):
        compilation = self._complete_compilation()
        state = self._tts_state(compilation)
        state["chunks"][0]["word_timings"][0]["end"] += 0.1
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(CompilationStoryboardError, "word timing"):
                build_storyboard(compilation, Path(temp), tts_state=state)

    def test_background_video_must_stay_under_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            video = Path(outside) / "loop.mp4"
            video.write_bytes(b"fixture")
            with self.assertRaisesRegex(CompilationStoryboardError, "under artifact_root"):
                compilation = self._complete_compilation()
                build_storyboard(
                    compilation, Path(temp), background_video=video,
                    tts_state=self._tts_state(compilation),
                )

    def test_storyboard_stores_background_as_artifact_relative_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video = root / "assets" / "loop.mp4"
            video.parent.mkdir()
            video.write_bytes(b"fixture")
            compilation = self._complete_compilation()
            storyboard = build_storyboard(
                compilation,
                root,
                background_video=video,
                tts_state=self._tts_state(compilation),
            )
        self.assertEqual(storyboard["background_video"]["local_path"], "assets/loop.mp4")

    def test_exact_story_beats_drive_scene_boundaries_without_changing_narration(self):
        compilation = self._complete_compilation()
        narration = compilation["stories"][0]["narration_ru"]
        first, second = narration.split(" Утром", 1)
        compilation["stories"][0]["story_beats"] = [first, "Утром" + second]
        with tempfile.TemporaryDirectory() as temp:
            storyboard = build_storyboard(
                compilation, Path(temp), tts_state=self._tts_state(compilation),
            )
        story_slides = [slide for slide in storyboard["slides"] if slide["segment_id"] == "story_abc"]
        self.assertEqual({slide["beat_index"] for slide in story_slides}, {1, 2})
        self.assertEqual(storyboard["creative_manifest"]["text_timing_coverage"], 1.0)

    def test_long_sentence_prefers_clause_boundaries_over_fixed_word_slicing(self):
        compilation = self._complete_compilation()
        compilation["stories"][0]["narration_ru"] = (
            "Сначала я увидел записку у двери и решил ничего не трогать в полной тишине несколько минут подряд, "
            "а потом позвонил соседу и дождался точного спокойного объяснения всего происходящего."
        )
        with tempfile.TemporaryDirectory() as temp:
            storyboard = build_storyboard(
                compilation, Path(temp), tts_state=self._tts_state(compilation),
            )
        chunks = [
            slide["narration_text"] for slide in storyboard["slides"]
            if slide["segment_id"] == "story_abc"
        ]
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith(","))
        self.assertTrue(chunks[1].startswith("а потом"))

    def test_long_story_schedules_three_to_five_stable_visual_scenes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compilation = self._complete_compilation()
            compilation["stories"][0]["narration_ru"] = " ".join(
                f"Подтвержденная сцена номер {index} постепенно меняет ход истории."
                for index in range(1, 321)
            )
            assets = []
            for index, color in enumerate(("#264653", "#2a9d8f", "#e9c46a", "#e76f51"), start=1):
                path = root / f"scene-{index}.png"
                Image.new("RGB", (640, 360), color).save(path)
                assets.append({
                    "download_status": "verified", "local_path": str(path),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                })
            compilation["stories"][0]["generated_media"] = assets
            storyboard = build_storyboard(
                compilation, root, tts_state=self._tts_state(compilation),
            )

        story_slides = [slide for slide in storyboard["slides"] if slide["segment_id"] == "story_abc"]
        self.assertGreater(len({slide["page_index"] for slide in story_slides}), 20)
        page_word_counts = {}
        for slide in story_slides:
            page_word_counts[slide["page_index"]] = len(slide["display_text"].split())
        self.assertGreater(max(page_word_counts.values()), 42)
        scene_ids = list(dict.fromkeys(slide["visual_scene_id"] for slide in story_slides))
        self.assertEqual(len(scene_ids), 5)
        self.assertEqual(len({slide["visual"]["sha256"] for slide in story_slides}), 4)
        for scene_id in scene_ids:
            scene_hashes = {
                slide["visual"]["sha256"] for slide in story_slides
                if slide["visual_scene_id"] == scene_id
            }
            self.assertEqual(len(scene_hashes), 1)
        schedules = storyboard["creative_manifest"]["story_visual_schedules"]
        self.assertEqual(schedules[0]["scene_count"], 5)
        self.assertEqual(schedules[0]["visual_count"], 4)
        self.assertTrue(story_slides[-1]["show_actions"])
        self.assertFalse(any(slide["show_actions"] for slide in story_slides[:-1]))


if __name__ == "__main__":
    unittest.main()
