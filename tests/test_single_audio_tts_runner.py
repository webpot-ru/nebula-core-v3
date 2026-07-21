import json
import tempfile
import unittest
from pathlib import Path

from acc1_narration_profiles import RELATIONSHIPS_FAMILY_PROFILE_ID, resolve_narration_profile
from single_audio_tts_runner import run_single_audio_tts


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
        self.assertEqual(request["status"], "COMPLETE")
        self.assertTrue(srt_exists)


if __name__ == "__main__":
    unittest.main()
