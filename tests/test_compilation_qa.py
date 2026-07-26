import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import acc1_episode_manifest
from acc1_visual_contract import (
    EDITORIAL_MOTION_MODE,
    INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
    MASCOT_SAFE_X,
)
from acc1_editorial_motion import bind_payload as bind_editorial_payload
from compilation_narration import build_compilation_segments
from compilation_qa import (
    _validate_editorial_motion_creative_contract,
    run_qa,
    validate_tts_state,
)
from compilation_storyboard import build_storyboard
from compilation_tts_runner import _canonical_hash, _state_timing_contract
from compilation_audio_mix import build_pause_map, canonical_hash as audio_canonical_hash
from acc1_cinematic_shots import write_caption_srt
from acc1_narration_profiles import (
    NARRATION_PROFILE_IDS_BY_PILLAR,
    resolve_narration_boundary_contract,
    resolve_narration_profile,
)


def fixture_compilation():
    stories = []
    for index in range(1, 4):
        body = f"Source body {index}. Ending {index}."
        stories.append({
            "title_ru": f"История {index}",
            "narration_ru": " ".join(["страх"] * 2000),
            "narration_role": "narrator",
            "disclosure": "This is fiction from Reddit.",
            "ending_preserved_evidence": f"Ending {index}.",
            "change_ledger": [],
            "invented_factual_claims": [],
            "editorial_review": {"verdict": "PASS", "issues": []},
            "source_snapshot": {
                "post_id": str(index), "source_url": f"https://reddit/{index}",
                "subreddit": "r/nosleep", "title": f"Story {index}", "body": body,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "truth_mode": "fiction", "source_media": [],
            },
        })
    disclosure = "Это художественные истории с Reddit."
    return {
        "title_ru": "Три истории с Reddit",
        "truth_disclosure_ru": disclosure,
        "intro_ru": f"Сегодня читаем три законченные истории. {disclosure}",
        "outro_ru": "Какая история запомнилась вам сильнее?",
        "rights_mode": "test_only_not_cleared", "publication_authorized": False,
        "revision_count": 0, "stories": stories,
        "editorial_review": {"verdict": "PASS", "issues": []},
    }


class CompilationQaTests(unittest.TestCase):
    def test_editorial_qa_accepts_ink_profile_and_validates_its_art_direction(self):
        scene = {
            "kind": "editorial_motion_scene",
            "presentation": "story",
            "start_sec": 0,
            "end_sec": 20,
            "duration_sec": 20,
            "narration_text": "история",
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "story_family": "work",
            "page_layout": "hero_left_details_right",
            "motion": {"module": "living_photo_depth", "seek_safe": True},
            "factual_text_rendering": "html_svg_only",
            "asset_family_id": "pack-1",
            "assets": [],
        }
        motion_plan = bind_editorial_payload({
            "version": 2,
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "scene_count": 1,
            "module_usage": {"living_photo_depth": 1},
            "scenes": [scene],
        }, "motion_plan_sha256")
        caption_track = bind_editorial_payload({
            "version": 1,
            "cues": [],
        }, "caption_track_sha256")
        storyboard = {
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "timeline_duration_sec": 20,
            "motion_plan": motion_plan,
            "caption_track": caption_track,
        }
        render_report = {
            "visual_mode": EDITORIAL_MOTION_MODE,
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "renderer": "hyperframes",
            "hyperframes_check_passed": True,
            "background_video_used": False,
            "factual_text_rendering": "html_svg_only",
            "duration_sec": 20,
        }
        creative_manifest = {
            "mode": EDITORIAL_MOTION_MODE,
            "style_profile": INK_GOUACHE_STORY_PAGES_STYLE_PROFILE,
            "background_video_required": False,
            "visual_contract": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            failures = _validate_editorial_motion_creative_contract(
                {"intro_ru": "", "outro_ru": "", "stories": []},
                storyboard,
                render_report,
                creative_manifest,
                [scene],
                Path(directory),
            )
            self.assertFalse(any("unsupported" in item for item in failures))
            self.assertFalse(any("style profile drifted" in item for item in failures))
            self.assertFalse(any("invalid Ink & Gouache art direction" in item for item in failures))
            render_report.update({
                "renderer": "hyperframes_segmented",
                "segment_count": 1,
                "segment_max_duration_sec": 120,
                "segments": [{"index": 1, "duration_sec": 20}],
                "captions_burned": True,
            })
            failures = _validate_editorial_motion_creative_contract(
                {"intro_ru": "", "outro_ru": "", "stories": []},
                storyboard,
                render_report,
                creative_manifest,
                [scene],
                Path(directory),
            )
            self.assertFalse(any("passing HyperFrames" in item for item in failures))
            self.assertFalse(any("segment inventory" in item for item in failures))
            self.assertFalse(any("bounded duration" in item for item in failures))
            render_report["segments"][0]["duration_sec"] = 121
            failures = _validate_editorial_motion_creative_contract(
                {"intro_ru": "", "outro_ru": "", "stories": []},
                storyboard,
                render_report,
                creative_manifest,
                [scene],
                Path(directory),
            )
            self.assertTrue(any("bounded duration" in item for item in failures))
            scene["page_layout"] = "repeated_old_grid"
            failures = _validate_editorial_motion_creative_contract(
                {"intro_ru": "", "outro_ru": "", "stories": []},
                storyboard,
                render_report,
                creative_manifest,
                [scene],
                Path(directory),
            )
            self.assertTrue(any("invalid Ink & Gouache art direction" in item for item in failures))

    def test_role_aware_tts_qa_rejects_comment_voice_fallback(self):
        state = {
            "status": "COMPLETE",
            "required_model_id": "eleven_v3",
            "final_audio_sha256": "1" * 64,
            "narration_plan_sha256": "2" * 64,
            "publication_authorized": False,
            "chunks": [{
                "status": "COMPLETE",
                "model_id": "eleven_v3",
                "voice_role": "comment",
                "voice_id": "narrator-voice",
                "audio_sha256": "3" * 64,
            }],
        }
        failures = validate_tts_state(
            state,
            expected_voice_id="narrator-voice",
            expected_comment_voice_id="comment-voice",
        )
        self.assertTrue(any("comment voice_id" in item for item in failures))
        self.assertTrue(any("fell back to narrator" in item for item in failures))

    def test_tts_qa_enforces_bundle_boundary_speed_and_checksum(self):
        profile = resolve_narration_profile(
            NARRATION_PROFILE_IDS_BY_PILLAR["relationships_family"],
            pillar_id="relationships_family",
        )
        contract = resolve_narration_boundary_contract(
            profile,
            episode_format="BUNDLE",
            source_count=2,
        )
        state = {
            "status": "COMPLETE",
            "required_model_id": "eleven_v3",
            "final_audio_sha256": "1" * 64,
            "narration_plan_sha256": "2" * 64,
            "publication_authorized": False,
            "narration_boundary_contract": contract,
            "narration_boundary_contract_sha256": contract[
                "narration_boundary_contract_sha256"
            ],
            "narration_boundary_policy_id": contract["policy_id"],
            "episode_format": "BUNDLE",
            "boundary_source_count": 2,
            "chunks": [{
                "status": "COMPLETE",
                "model_id": "eleven_v3",
                "voice_role": "narrator",
                "voice_id": "narrator-voice",
                "audio_sha256": "3" * 64,
                "logical_segment_id": "transition_01",
                "logical_segment_kind": "transition",
                "effective_speed": contract["effective_transition_speed"],
                "narration_boundary_contract_sha256": contract[
                    "narration_boundary_contract_sha256"
                ],
                "narration_boundary_policy_id": contract["policy_id"],
                "episode_format": "BUNDLE",
                "boundary_source_count": 2,
            }],
        }
        failures = validate_tts_state(
            state,
            expected_voice_id="narrator-voice",
            expected_narration_boundary_contract=contract,
        )
        self.assertEqual(failures, [])
        state["chunks"][0]["effective_speed"] = contract["base_speed"]
        failures = validate_tts_state(
            state,
            expected_voice_id="narrator-voice",
            expected_narration_boundary_contract=contract,
        )
        self.assertTrue(any("effective speed" in item for item in failures))

    @staticmethod
    def _metadata():
        return {
            "packaging_options": [
                {"youtube_title": f"Title {i}", "thumbnail_text": f"Text {i}", "angle": f"angle-{i}"}
                for i in range(3)
            ],
            "youtube_description": (
                "Это художественные истории с Reddit. "
                + " ".join(f"https://reddit/{i}" for i in range(1, 4))
            ),
            "language": "ru",
        }

    @staticmethod
    def _creative_hash(value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _episode_plan(compilation, *, historical=True, visual_mode=None):
        queue = {
            "channel_id": "acc1",
            "entries": [
                {
                    "post_id": story["source_snapshot"]["post_id"],
                    "source_body": story["source_snapshot"]["body"],
                    "source_body_sha256": story["source_snapshot"]["body_sha256"],
                }
                for story in compilation["stories"]
            ],
        }
        review = {"status": "review_ready", "top_topics": [
            {"post_id": story["source_snapshot"]["post_id"]}
            for story in compilation["stories"]
        ]}
        greenlight = {
            "channel_id": "acc1",
            "pilot_id": "pilot_bundle_01",
            "format": "BUNDLE",
            "pillar": "strange_dark_unexplained",
            "publication_authorized": False,
            "sources": [
                {
                    "post_id": story["source_snapshot"]["post_id"],
                    "source_body_sha256": story["source_snapshot"]["body_sha256"],
                    "truth_mode": story["source_snapshot"]["truth_mode"],
                }
                for story in compilation["stories"]
            ],
        }
        config = {"channel_id": "acc1", "format": "reddit_pages"}
        daily_plan = {
            "episode_key": "acc1/2026-07-14/pilot_bundle_01",
            "production_date": "2026-07-14",
            "pilot_id": "pilot_bundle_01",
            "format": "BUNDLE",
            "pillar": "strange_dark_unexplained",
            "publication_authorized": False,
        }
        plan = acc1_episode_manifest.build_episode_manifest(
            episode_key="acc1/2026-07-14/pilot_bundle_01",
            episode_date="2026-07-14",
            pilot_id="pilot_bundle_01",
            format_id="BUNDLE",
            pillar="strange_dark_unexplained",
            source_queue=queue,
            topic_review=review,
            greenlight=greenlight,
            config=config,
            daily_plan=daily_plan,
            git_sha="1234567890abcdef1234567890abcdef12345678",
            provider_settings={
                "tts": {"model_id": "eleven_v3", "voice_id": "voice-primary"},
                "translation": {"model": "gemini-3.5-flash"},
            },
        )
        if historical:
            # Preserve a genuine historical manifest shape for the baseline test.
            # v1 has no mode/profile/mix obligations.
            plan["version"] = 1
            for field in (
                "visual_mode", "narration_profile_id", "narration_profile_sha256",
                "shot_plan_contract", "caption_track_contract", "audio_mix_contract",
            ):
                plan.pop(field, None)
            plan["episode_plan_sha256"] = acc1_episode_manifest.canonical_hash({
                key: value for key, value in plan.items() if key != "episode_plan_sha256"
            })
        elif visual_mode:
            # Rebuild so all immutable v2 contracts bind the requested mode.
            plan = acc1_episode_manifest.build_episode_manifest(
                episode_key="acc1/2026-07-14/pilot_bundle_01", episode_date="2026-07-14",
                pilot_id="pilot_bundle_01", format_id="BUNDLE", pillar="strange_dark_unexplained",
                source_queue=queue, topic_review=review, greenlight=greenlight, config=config,
                daily_plan=daily_plan, git_sha="1234567890abcdef1234567890abcdef12345678",
                provider_settings={"tts": {"model_id": "eleven_v3", "voice_id": "voice-primary"}, "translation": {"model": "gemini-3.5-flash"}},
                visual_mode=visual_mode,
            )
        return plan

    def _complete_case(self, root):
        compilation = fixture_compilation()
        episode_plan = self._episode_plan(compilation)
        plan_hash = episode_plan["episode_plan_sha256"]
        daily_plan_sha256 = episode_plan["daily_plan_sha256"]
        compilation["episode_plan_sha256"] = plan_hash
        compilation["daily_plan_sha256"] = daily_plan_sha256
        metadata = self._metadata()
        metadata["episode_plan_sha256"] = plan_hash
        metadata["daily_plan_sha256"] = daily_plan_sha256

        audio = root / "narration.mp3"
        audio.write_bytes(b"synthetic-final-audio")
        audio_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
        chunks = []
        raw_duration = 0.0
        for segment in build_compilation_segments(compilation):
            words = segment["text"].split()
            duration = len(words) * 0.25
            word_timings = [
                {
                    "word": word,
                    "start": round(index * 0.25, 3),
                    "end": round((index + 1) * 0.25, 3),
                    "timing_source": "estimated_from_audio_duration",
                }
                for index, word in enumerate(words)
            ]
            chunks.append({
                "status": "COMPLETE",
                "model_id": "eleven_v3",
                "voice_id": "voice-primary",
                "audio_sha256": "a" * 64,
                "chunk_id": f"{segment['segment_id']}__001",
                "chunk_index": 1,
                "logical_segment_id": segment["segment_id"],
                "logical_segment_kind": segment["kind"],
                "voice_role": segment["voice_role"],
                "episode_plan_sha256": plan_hash,
                "daily_plan_sha256": daily_plan_sha256,
                "text": segment["text"],
                "text_sha256": hashlib.sha256(segment["text"].encode()).hexdigest(),
                "audio_duration_sec": duration,
                "timing_source": "estimated_from_audio_duration",
                "word_timings": word_timings,
                "word_timings_sha256": _canonical_hash(word_timings),
            })
            raw_duration += duration
        tts = {
            "status": "COMPLETE",
            "required_model_id": "eleven_v3",
            "chunks": chunks,
            "final_audio_sha256": audio_hash,
            "episode_plan_sha256": plan_hash,
            "daily_plan_sha256": daily_plan_sha256,
            "narration_plan_sha256": "4" * 64,
            "timing_contract_version": 1,
            "final_audio_duration_sec": raw_duration,
            "raw_chunk_duration_sec": raw_duration,
            "timeline_scale": 1.0,
            "publication_authorized": False,
        }
        tts["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(tts))

        thumbnail = root / "thumbnail.png"
        Image.new("RGB", (1280, 720), "#223344").save(thumbnail)
        video = root / "final.mp4"
        video.write_bytes(b"synthetic-final-video")
        storyboard = build_storyboard(compilation, root, tts_state=tts)
        manifest = storyboard["creative_manifest"]
        planned_duration = sum(float(slide["duration_sec"]) for slide in storyboard["slides"])
        expected_max_slide = (
            max(float(slide["duration_sec"]) for slide in storyboard["slides"])
            * 3000
            / planned_duration
        )
        render_report = {
            "status": "ok", "resolution": [1920, 1080], "audio_merged": True,
            "duration_sec": 3000, "audio_duration_sec": 3000,
            "audio_sha256": audio_hash,
            "max_slide_duration_sec": expected_max_slide, "slide_timing_coverage": 1.0,
            "text_timing_coverage": 1.0, "reddit_page_count": len(storyboard["slides"]),
            "creative_manifest_sha256": self._creative_hash(manifest),
            "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "mascot_safe_x": MASCOT_SAFE_X,
            "episode_plan_sha256": plan_hash,
            "daily_plan_sha256": daily_plan_sha256,
            "narration_plan_sha256": tts["narration_plan_sha256"],
            "publication_authorized": False,
        }
        artifact_hashes = {
            "script_sha256": self._creative_hash(compilation),
            "audio_sha256": audio_hash,
            "metadata_sha256": self._creative_hash(metadata),
            "storyboard_sha256": self._creative_hash(storyboard),
            "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "thumbnail_sha256": hashlib.sha256(thumbnail.read_bytes()).hexdigest(),
        }
        return {
            "compilation": compilation,
            "metadata": metadata,
            "tts": tts,
            "storyboard": storyboard,
            "render_report": render_report,
            "episode_plan": episode_plan,
            "artifact_hashes": artifact_hashes,
            "audio": audio,
            "video": video,
            "thumbnail": thumbnail,
        }

    def _complete_v2_case(self, root, *, cinematic=False):
        """Build a fully bound synthetic v2 artifact without invoking FFmpeg."""
        case = self._complete_case(root)
        mode = "cinematic_story_v1" if cinematic else "reddit_pages"
        compilation = case["compilation"]
        compilation["visual_mode"] = mode
        plan = self._episode_plan(compilation, historical=False, visual_mode=mode)
        plan_hash = plan["episode_plan_sha256"]
        for payload in (compilation, case["metadata"], case["tts"], case["render_report"]):
            payload["episode_plan_sha256"] = plan_hash
            payload["daily_plan_sha256"] = plan["daily_plan_sha256"]
        profile = resolve_narration_profile(
            plan["narration_profile_id"], pillar_id="strange_dark_unexplained",
        )
        tts = case["tts"]
        tts["narration_profile_id"] = profile["profile_id"]
        tts["narration_profile_sha256"] = profile["profile_sha256"]
        tts["narration_pillar_id"] = profile["pillar_id"]
        for index, chunk in enumerate(tts["chunks"]):
            chunk.update({
                "episode_plan_sha256": plan_hash,
                "daily_plan_sha256": plan["daily_plan_sha256"],
                "narration_profile_id": profile["profile_id"],
                "narration_profile_sha256": profile["profile_sha256"],
                "audio_path": f"chunks/{index}.mp3",
                "is_last_in_beat": True,
                "is_last_in_segment": True,
            })
        tts["timing_contract_sha256"] = _canonical_hash(_state_timing_contract(tts))
        pause_map = build_pause_map(tts)
        input_chunks = [{
            key: chunk[key] for key in (
                "chunk_id", "audio_path", "audio_sha256", "audio_duration_sec",
                "timing_source", "word_timings_sha256",
            )
        } for chunk in tts["chunks"]]
        loudness = profile["voice_only_loudness"]
        mix_report = {
            "version": 1, "status": "PASS", "mode": "voice_only",
            "episode_plan_sha256": plan_hash, "daily_plan_sha256": plan["daily_plan_sha256"],
            "narration_plan_sha256": tts["narration_plan_sha256"],
            "timing_contract_sha256": tts["timing_contract_sha256"],
            "narration_profile_id": profile["profile_id"],
            "narration_profile_sha256": profile["profile_sha256"],
            "input_chunks": input_chunks, "input_chunks_sha256": audio_canonical_hash(input_chunks),
            "pause_map_sha256": pause_map["pause_map_sha256"],
            "output_sha256": case["tts"]["final_audio_sha256"],
            "expected_timeline_duration_sec": pause_map["timeline_duration_sec"],
            "output_duration_sec": pause_map["timeline_duration_sec"],
            "duration_tolerance_sec": 0.25,
            "loudness": {
                "target_integrated_lufs": loudness["integrated_lufs"],
                "tolerance_lu": loudness["tolerance_lu"],
                "max_true_peak_dbtp": loudness["max_true_peak_dbtp"],
                "measured_integrated_lufs": loudness["integrated_lufs"],
                "measured_true_peak_dbtp": loudness["max_true_peak_dbtp"],
                "integrated_loudness_pass": True, "true_peak_pass": True,
            },
            "failures": [], "network_used": False, "publication_authorized": False,
        }
        mix_report["audio_mix_report_sha256"] = audio_canonical_hash(mix_report)
        if cinematic:
            for index, story in enumerate(compilation["stories"]):
                image = root / f"scene-{index}.png"
                Image.new("RGB", (32, 18), "#445566").save(image)
                story["generated_media"] = [{
                    "download_status": "verified", "artifact_path": image.name,
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                }]
        storyboard = build_storyboard(
            compilation, root, tts_state=tts, visual_mode=mode,
            pause_map=pause_map, audio_mix_report=mix_report,
        )
        manifest = storyboard["creative_manifest"]
        duration = pause_map["timeline_duration_sec"]
        render = case["render_report"]
        render.update({
            "duration_sec": duration, "audio_duration_sec": duration,
            "audio_sha256": tts["final_audio_sha256"], "visual_mode": mode,
            "creative_manifest_sha256": self._creative_hash(manifest),
            "pause_map_sha256": pause_map["pause_map_sha256"],
            "audio_mix_report_sha256": mix_report["audio_mix_report_sha256"],
        })
        if cinematic:
            srt = write_caption_srt(storyboard["caption_track"], root / "captions.srt")
            motion = [{"shot_id": slide["shot_id"], "visual_sha256": slide["visual_sha256"], "motion": slide["motion"]} for slide in storyboard["slides"]]
            story_lengths = [slide["duration_sec"] for slide in storyboard["slides"] if slide["presentation"] == "story"]
            render.update({
                "reddit_page_count": 0, "background_video_used": False,
                "fullscreen_images_verified": True, "shot_count": len(storyboard["slides"]),
                "shot_plan_sha256": storyboard["shot_plan_sha256"],
                "caption_track_sha256": storyboard["caption_track_sha256"],
                "motion_evidence": motion, "motion_evidence_sha256": self._creative_hash(motion),
                "story_shot_duration_min_sec": min(story_lengths),
                "story_shot_duration_max_sec": max(story_lengths),
                "caption_srt": str(srt), "caption_srt_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
            })
        else:
            planned = sum(slide["duration_sec"] for slide in storyboard["slides"])
            render["max_slide_duration_sec"] = max(slide["duration_sec"] for slide in storyboard["slides"]) * duration / planned
            render["reddit_page_count"] = len(storyboard["slides"])
        artifacts = {
            "script_sha256": self._creative_hash(compilation), "audio_sha256": tts["final_audio_sha256"],
            "metadata_sha256": self._creative_hash(case["metadata"]), "storyboard_sha256": self._creative_hash(storyboard),
            "video_sha256": hashlib.sha256(case["video"].read_bytes()).hexdigest(),
            "thumbnail_sha256": hashlib.sha256(case["thumbnail"].read_bytes()).hexdigest(),
        }
        case.update({"episode_plan": plan, "storyboard": storyboard, "render_report": render,
                     "pause_map": pause_map, "audio_mix_report": mix_report, "artifact_hashes": artifacts})
        return case

    def test_passes_complete_artifact_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                )
        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertTrue(result["thumbnail_sha256"])
        self.assertEqual(result["video_sha256"], hashlib.sha256(b"synthetic-final-video").hexdigest())
        self.assertEqual(result["episode_plan_sha256"], case["episode_plan"]["episode_plan_sha256"])
        self.assertTrue(result["truth_disclosure_audible"])
        self.assertTrue(result["truth_disclosure_visible_in_metadata"])

    def test_passes_v2_mixed_reddit_pages_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_v2_case(root)
            probe = {"streams": [
                {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ], "format": {"duration": str(case["render_report"]["audio_duration_sec"])}}
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"], case["storyboard"], case["render_report"],
                    artifact_root=root, video_path=case["video"], thumbnail_path=case["thumbnail"], audio_path=case["audio"],
                    expected_voice_id="voice-primary", episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                    pause_map=case["pause_map"], audio_mix_report=case["audio_mix_report"],
                )
        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertEqual(result["visual_mode"], "reddit_pages")
        self.assertEqual(result["pause_map_sha256"], case["pause_map"]["pause_map_sha256"])
        self.assertEqual(result["audio_mix_report_sha256"], case["audio_mix_report"]["audio_mix_report_sha256"])
        self.assertEqual(result["timing_contract_sha256"], case["tts"]["timing_contract_sha256"])

    def test_passes_v2_cinematic_srt_contract_and_blocks_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_v2_case(root, cinematic=True)
            probe = {"streams": [
                {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ], "format": {"duration": str(case["render_report"]["audio_duration_sec"])}}
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"], case["storyboard"], case["render_report"],
                    artifact_root=root, video_path=case["video"], thumbnail_path=case["thumbnail"], audio_path=case["audio"],
                    expected_voice_id="voice-primary", episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                    pause_map=case["pause_map"], audio_mix_report=case["audio_mix_report"],
                )
                self.assertEqual(result["status"], "PASS", result["failures"])
                srt = Path(case["render_report"]["caption_srt"])
                srt.write_text(srt.read_text(encoding="utf-8").replace("Сегодня", "Завтра", 1), encoding="utf-8")
                tampered = run_qa(
                    case["compilation"], case["metadata"], case["tts"], case["storyboard"], case["render_report"],
                    artifact_root=root, video_path=case["video"], thumbnail_path=case["thumbnail"], audio_path=case["audio"],
                    expected_voice_id="voice-primary", episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                    pause_map=case["pause_map"], audio_mix_report=case["audio_mix_report"],
                )
        self.assertEqual(tampered["status"], "BLOCKED")
        self.assertTrue(any("caption SRT" in item for item in tampered["failures"]))

    def test_actual_runtime_must_fit_locked_format_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                    target_duration_minutes=[18, 30],
                )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["runtime_target_minutes"], [18.0, 30.0])
        self.assertEqual(result["actual_runtime_minutes"], 50.0)
        self.assertTrue(
            any("outside the locked 18-30 minute target" in item for item in result["failures"])
        )

    def test_blocks_downstream_episode_plan_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["metadata"]["episode_plan_sha256"] = "9" * 64
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("metadata episode_plan_sha256" in item for item in result["failures"]))

    def test_blocks_swapped_final_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["audio"].write_bytes(b"different-audio-after-tts")
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                )
        self.assertTrue(any("actual narration audio" in item for item in result["failures"]))

    def test_blocks_missing_audible_and_metadata_disclosure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            disclosure_chunk = next(
                item for item in case["tts"]["chunks"]
                if item["logical_segment_id"] == "intro"
            )
            disclosure_chunk["text"] = "Сегодня читаем три законченные истории."
            case["metadata"]["youtube_description"] = " ".join(
                f"https://reddit/{index}" for index in range(1, 4)
            )
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                )
        self.assertFalse(result["truth_disclosure_audible"])
        self.assertFalse(result["truth_disclosure_visible_in_metadata"])
        self.assertTrue(any("audible truth disclosure" in item for item in result["failures"]))
        self.assertTrue(any("visible truth disclosure" in item for item in result["failures"]))

    def test_blocks_wrong_model_and_missing_source_url(self):
        compilation = fixture_compilation()
        metadata = {"packaging_options": [], "youtube_description": "", "language": "ru"}
        tts = {"status": "COMPLETE", "required_model_id": "eleven_v2", "chunks": [], "final_audio_sha256": ""}
        storyboard = {"format": "compilation_16x9", "resolution": [1920, 1080], "slides": [{"slide_id": "intro", "kind": "title"}]}
        report = {"status": "failed"}
        with tempfile.TemporaryDirectory() as temp:
            result = run_qa(compilation, metadata, tts, storyboard, report, artifact_root=Path(temp))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("eleven_v3" in item for item in result["failures"]))

    def test_generic_episode_uses_generic_script_and_packaging_contracts(self):
        compilation = fixture_compilation()
        compilation["episode_format"] = "BUNDLE"
        with tempfile.TemporaryDirectory() as temp, \
             patch("compilation_qa.validate_episode_script", return_value={
                 "status": "PASS", "failures": [], "story_count": 3,
             }) as script_validator, \
             patch("compilation_qa.validate_episode_packaging", return_value=[]) as packaging_validator, \
             patch("compilation_qa.validate_compilation", side_effect=AssertionError("legacy validator called")), \
             patch("compilation_qa.validate_metadata", side_effect=AssertionError("legacy metadata called")):
            result = run_qa(
                compilation,
                {"youtube_description": compilation["truth_disclosure_ru"]},
                {}, {}, {}, artifact_root=Path(temp),
                episode_plan={}, topic_playoff={},
            )
        self.assertEqual(result["status"], "BLOCKED")
        script_validator.assert_called_once()
        packaging_validator.assert_called_once()

    def test_blocks_wrong_voice_excessive_slide_and_missing_thumbnail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["tts"]["chunks"][0]["voice_id"] = "wrong"
            case["render_report"]["max_slide_duration_sec"] = 12.251
            result = run_qa(
                case["compilation"], case["metadata"], case["tts"],
                case["storyboard"], case["render_report"], artifact_root=root,
                audio_path=case["audio"],
                expected_voice_id="voice-primary", episode_plan=case["episode_plan"],
                artifact_hashes=case["artifact_hashes"],
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("voice_id" in item for item in result["failures"]))
        self.assertTrue(any("longer than" in item for item in result["failures"]))
        self.assertIn("actual thumbnail is required", result["failures"])

    def test_blocks_reddit_actions_outside_the_final_story_chunk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["storyboard"]["slides"][0]["show_actions"] = True
            result = run_qa(
                case["compilation"], case["metadata"], case["tts"],
                case["storyboard"], case["render_report"], artifact_root=root,
                thumbnail_path=case["thumbnail"],
                audio_path=case["audio"], expected_voice_id="voice-primary",
                episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("forbidden outside story" in item for item in result["failures"]))

    def test_blocks_missing_background_required_by_creative_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["storyboard"]["creative_manifest"]["background_video_required"] = True
            case["render_report"]["creative_manifest_sha256"] = self._creative_hash(
                case["storyboard"]["creative_manifest"]
            )
            result = run_qa(
                case["compilation"], case["metadata"], case["tts"],
                case["storyboard"], case["render_report"], artifact_root=root,
                thumbnail_path=case["thumbnail"],
                audio_path=case["audio"], expected_voice_id="voice-primary",
                episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("requires a background video" in item for item in result["failures"]))

    def test_malformed_manifest_and_sidecar_numbers_block_without_raising(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["episode_plan"]["version"] = "not-a-number"
            malformed_pause_map = {"timeline_duration_sec": "nope", "entries": []}
            malformed_mix = {"output_duration_sec": "nope", "loudness": {}}
            result = run_qa(
                case["compilation"], case["metadata"], case["tts"],
                case["storyboard"], case["render_report"], artifact_root=root,
                audio_path=case["audio"], expected_voice_id="voice-primary",
                episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                pause_map=malformed_pause_map, audio_mix_report=malformed_mix,
            )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("self-hash" in item for item in result["failures"]))

    def test_blocks_non_h264_or_non_aac_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            probe = {
                "streams": [
                    {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "hevc", "avg_frame_rate": "24/1"},
                    {"codec_type": "audio", "codec_name": "mp3"},
                ],
                "format": {"duration": "3000"},
            }
            with patch("compilation_qa.ffprobe_json", return_value=probe):
                result = run_qa(
                    case["compilation"], case["metadata"], case["tts"],
                    case["storyboard"], case["render_report"], artifact_root=root,
                    video_path=case["video"], thumbnail_path=case["thumbnail"],
                    audio_path=case["audio"], expected_voice_id="voice-primary",
                    episode_plan=case["episode_plan"], artifact_hashes=case["artifact_hashes"],
                )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("H.264 at 30 fps" in item for item in result["failures"]))
        self.assertTrue(any("AAC" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
