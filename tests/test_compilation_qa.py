import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import acc1_episode_manifest
from acc1_visual_contract import MASCOT_SAFE_X
from compilation_narration import build_compilation_segments
from compilation_qa import run_qa, validate_tts_state
from compilation_storyboard import build_storyboard
from compilation_tts_runner import _canonical_hash, _state_timing_contract


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
    def _episode_plan(compilation):
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
        return acc1_episode_manifest.build_episode_manifest(
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

    def test_passes_complete_artifact_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
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
        self.assertEqual(result["status"], "PASS", result["failures"])
        self.assertTrue(result["thumbnail_sha256"])
        self.assertEqual(result["video_sha256"], hashlib.sha256(b"synthetic-final-video").hexdigest())
        self.assertEqual(result["episode_plan_sha256"], case["episode_plan"]["episode_plan_sha256"])
        self.assertTrue(result["truth_disclosure_audible"])
        self.assertTrue(result["truth_disclosure_visible_in_metadata"])

    def test_actual_runtime_must_fit_locked_format_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
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
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("metadata episode_plan_sha256" in item for item in result["failures"]))

    def test_blocks_swapped_final_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = self._complete_case(root)
            case["audio"].write_bytes(b"different-audio-after-tts")
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
            case["render_report"]["max_slide_duration_sec"] = 20.0
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


if __name__ == "__main__":
    unittest.main()
