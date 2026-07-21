import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acc1_narration_profiles import RELATIONSHIPS_FAMILY_PROFILE_ID, resolve_narration_profile
from single_audio_tts_runner import run_single_audio_tts
from translator_tts import fetch_subtitle_words


def compilation():
    disclosure = "Это художественная история с Reddit."
    return {
        "episode_plan_sha256": "1" * 64,
        "daily_plan_sha256": "2" * 64,
        "publication_authorized": False,
        "pillar": "relationships_family",
        "narration_profile_id": RELATIONSHIPS_FAMILY_PROFILE_ID,
        "truth_disclosure_ru": disclosure,
        "intro_ru": f"Начало выпуска. {disclosure}",
        "stories": [{
            "source_snapshot": {"post_id": "abc", "truth_mode": "fiction"},
            "narration_ru": "Первая история закончилась хорошо.",
            "narration_role": "narrator",
        }],
        "outro_ru": "Конец выпуска.",
    }


class SingleAudioTtsRunnerTests(unittest.TestCase):
    def test_fetches_json_alignment_from_described_output_asset(self):
        class Response:
            ok = True
            content = json.dumps({
                "words": [{"word": "Готово", "start": 0.0, "end": 0.7}],
            }).encode()

        payload = {
            "outputs": [{
                "type": "transcript json",
                "url": "https://cdn.example.test/task-output",
            }],
        }
        with patch("translator_tts.requests.get", return_value=Response()) as get:
            words = fetch_subtitle_words(payload, api_key="secret")
        self.assertEqual(words[0]["word"], "Готово")
        self.assertEqual(get.call_count, 1)

    def test_resume_polls_saved_task_without_posting_again(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "tts"
            output.mkdir()
            profile = resolve_narration_profile(
                RELATIONSHIPS_FAMILY_PROFILE_ID, pillar_id="relationships_family",
            )
            posts = []
            polls = []

            def forbidden_post(**kwargs):
                posts.append(kwargs)
                raise AssertionError("resume-only recovery must not submit a new task")

            def poll(**kwargs):
                polls.append(kwargs)
                kwargs["output_path"].write_bytes(b"master")
                text = " ".join([
                    "Начало выпуска. Это художественная история с Reddit.",
                    "Первая история закончилась хорошо.",
                    "Конец выпуска.",
                ])
                return {"success": True, "model_id": "eleven_v3", "words": [
                    {"word": token.rstrip(".!?,"), "start": index, "end": index + 0.8}
                    for index, token in enumerate(text.split())
                ]}

            request = {
                "version": 1,
                "status": "SUBMITTED",
                "text_sha256": "9e8bfe696313894338977a7738f4c329a811bc30575c1987825495b20d280912",
                "character_count": 118,
                "voice_id": "elevenlabs_voice",
                "model_id": "eleven_v3",
                "speed": profile["speed"],
                "voice_settings_json": profile["voice_settings_json"],
                "with_transcript": True,
                "pronunciation_dictionary_id": 72,
                "pronunciation_dictionary_sha256": "a" * 64,
                "provider_task_cap": 1,
                "publication_authorized": False,
                "task_id": "saved-task",
            }
            # Derive the exact immutable request fields from the same narration plan.
            from compilation_tts_runner import _canonical_hash, build_tts_chunks
            planned = build_tts_chunks(
                compilation(), voice_id="elevenlabs_voice",
                narration_profile_id=RELATIONSHIPS_FAMILY_PROFILE_ID,
                speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
                with_transcript=True, pronunciation_dictionary_id=72,
                pronunciation_dictionary_sha256="a" * 64,
            )
            master_text = " ".join(item["text"].strip() for item in planned)
            request["text_sha256"] = _canonical_hash(master_text)
            request["character_count"] = len(master_text)
            (output / "single-audio-request.json").write_text(json.dumps(request))

            def slice_audio(_source, destination, _start, _end):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"slice")

            def concat_with_pauses(_segments, logical_ids, destination, *, pause_sec):
                destination.write_bytes(b"paused")
                self.assertEqual(pause_sec, 0.9)
                return [
                    index for index in range(len(logical_ids) - 1)
                    if logical_ids[index] != logical_ids[index + 1]
                ]

            state = run_single_audio_tts(
                compilation(), output_dir=output, artifact_root=root,
                api_key="secret", voice_id="elevenlabs_voice",
                narration_profile_id=RELATIONSHIPS_FAMILY_PROFILE_ID,
                pronunciation_dictionary_id=72,
                pronunciation_dictionary_sha256="a" * 64,
                speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
                post_task=forbidden_post, poll_task=poll, slice_audio=slice_audio,
                concat_with_pauses=concat_with_pauses,
                probe_duration=lambda _path: 100.0, resume_only=True, sleeper=lambda _seconds: None,
            )

        self.assertEqual(posts, [])
        self.assertEqual([item["task_id"] for item in polls], ["saved-task"])
        self.assertEqual(polls[0]["timeout_seconds"], 14_400)
        self.assertEqual(state["provider_task_count"], 1)

    def test_one_provider_task_creates_master_srt_and_virtual_chunks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            posts = []
            polls = []

            def post(**kwargs):
                posts.append(kwargs)
                return {"success": True, "task_id": "one-task"}

            def poll(**kwargs):
                polls.append(kwargs["task_id"])
                kwargs["output_path"].write_bytes(b"master")
                text = posts[0]["text"]
                return {"success": True, "model_id": "eleven_v3", "words": [
                    {"word": token.rstrip(".!?,"), "start": index, "end": index + 0.8}
                    for index, token in enumerate(text.split())
                ]}

            def slice_audio(_source, output, _start, _end):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"slice")

            def concat_with_pauses(_segments, logical_ids, output, *, pause_sec):
                output.write_bytes(b"paused")
                return [
                    index for index in range(len(logical_ids) - 1)
                    if logical_ids[index] != logical_ids[index + 1]
                ]

            profile = resolve_narration_profile(
                RELATIONSHIPS_FAMILY_PROFILE_ID, pillar_id="relationships_family",
            )
            state = run_single_audio_tts(
                compilation(), output_dir=root / "tts", artifact_root=root,
                api_key="secret", voice_id="elevenlabs_voice",
                narration_profile_id=RELATIONSHIPS_FAMILY_PROFILE_ID,
                pronunciation_dictionary_id=72,
                pronunciation_dictionary_sha256="a" * 64,
                speed=profile["speed"], voice_settings_json=profile["voice_settings_json"],
                post_task=post, poll_task=poll, slice_audio=slice_audio,
                concat_with_pauses=concat_with_pauses,
                probe_duration=lambda _path: 100.0,
            )
            request = json.loads((root / "tts/single-audio-request.json").read_text())
            srt_exists = (root / "tts/narration.srt").is_file()
        self.assertEqual(len(posts), 1)
        self.assertEqual(polls, ["one-task"])
        self.assertTrue(posts[0]["with_transcript"])
        self.assertEqual(posts[0]["pronunciation_dictionary_id"], 72)
        self.assertEqual(state["provider_task_count"], 1)
        self.assertTrue(state["single_provider_task"])
        self.assertEqual(state["section_pause_sec"], 0.9)
        self.assertGreater(state["section_pause_count"], 0)
        self.assertEqual(request["status"], "COMPLETE")
        self.assertTrue(srt_exists)


if __name__ == "__main__":
    unittest.main()
