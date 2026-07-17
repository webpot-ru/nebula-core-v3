import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from acc1_narration_profiles import (
    NARRATION_PROFILES,
    STRANGE_DARK_UNEXPLAINED_PROFILE_ID,
    canonical_hash,
)
from compilation_audio_mix import (
    build_pause_map,
    mix_compilation_audio,
    verify_self_hash,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_state(chunks):
    profile = NARRATION_PROFILES[STRANGE_DARK_UNEXPLAINED_PROFILE_ID]
    return {
        "version": 3,
        "status": "COMPLETE",
        "episode_plan_sha256": "1" * 64,
        "daily_plan_sha256": "2" * 64,
        "narration_plan_sha256": "3" * 64,
        "timing_contract_sha256": "4" * 64,
        "narration_profile_id": profile["profile_id"],
        "narration_profile_sha256": profile["profile_sha256"],
        "narration_pillar_id": profile["pillar_id"],
        "chunks": chunks,
        "publication_authorized": False,
    }


def chunk(
    chunk_id,
    *,
    segment_id,
    segment_kind,
    beat_id,
    beat_index,
    audio_path,
    audio_sha256,
    duration,
    last_in_beat,
    last_in_segment,
):
    profile = NARRATION_PROFILES[STRANGE_DARK_UNEXPLAINED_PROFILE_ID]
    word_timings = [{
        "word": chunk_id,
        "start": 0.0,
        "end": duration,
        "timing_source": "estimated_from_audio_duration",
    }]
    return {
        "chunk_id": chunk_id,
        "logical_segment_id": segment_id,
        "logical_segment_kind": segment_kind,
        "semantic_beat_id": beat_id,
        "semantic_beat_index": beat_index,
        "audio_path": audio_path,
        "audio_sha256": audio_sha256,
        "audio_duration_sec": duration,
        "timing_source": "estimated_from_audio_duration",
        "word_timings": word_timings,
        "word_timings_sha256": canonical_hash(word_timings),
        "narration_profile_sha256": profile["profile_sha256"],
        "is_last_in_beat": last_in_beat,
        "is_last_in_segment": last_in_segment,
        "status": "COMPLETE",
    }


class CompilationAudioMixTests(unittest.TestCase):
    def test_pause_map_is_deterministic_and_uses_exact_boundary_types(self):
        chunks = [
            chunk(
                "intro__001",
                segment_id="intro",
                segment_kind="intro",
                beat_id="intro__beat_001",
                beat_index=1,
                audio_path="segments/intro.wav",
                audio_sha256="a" * 64,
                duration=1.0,
                last_in_beat=True,
                last_in_segment=True,
            ),
            chunk(
                "story__001",
                segment_id="story_a",
                segment_kind="story",
                beat_id="story_a__beat_001",
                beat_index=1,
                audio_path="segments/story-1.wav",
                audio_sha256="b" * 64,
                duration=2.0,
                last_in_beat=True,
                last_in_segment=False,
            ),
            chunk(
                "story__002",
                segment_id="story_a",
                segment_kind="story",
                beat_id="story_a__beat_002",
                beat_index=2,
                audio_path="segments/story-2.wav",
                audio_sha256="c" * 64,
                duration=2.0,
                last_in_beat=False,
                last_in_segment=False,
            ),
            chunk(
                "outro__001",
                segment_id="outro",
                segment_kind="outro",
                beat_id="outro__beat_001",
                beat_index=1,
                audio_path="segments/outro.wav",
                audio_sha256="d" * 64,
                duration=1.0,
                last_in_beat=True,
                last_in_segment=True,
            ),
        ]
        state = completed_state(chunks)
        first = build_pause_map(state)
        second = build_pause_map(state)
        self.assertEqual(first, second)
        self.assertTrue(verify_self_hash(first, "pause_map_sha256"))
        self.assertEqual(
            [entry["pause_kind"] for entry in first["entries"]],
            ["segment", "beat", "intra_beat", "none"],
        )
        self.assertEqual(first["entries"][-1]["pause_after_sec"], 0.0)
        self.assertAlmostEqual(
            first["timeline_duration_sec"],
            first["voice_duration_sec"] + first["pause_duration_sec"],
            places=6,
        )
        self.assertFalse(first["network_used"])
        self.assertFalse(first["publication_authorized"])

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg and ffprobe required",
    )
    def test_real_ffmpeg_voice_mix_is_loudness_measured_and_self_hashed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            segments = root / "segments"
            segments.mkdir()
            first_audio = segments / "first.wav"
            second_audio = segments / "second.wav"
            for frequency, output in ((330, first_audio), (440, second_audio)):
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi",
                    "-i", f"sine=frequency={frequency}:duration=3",
                    "-af", "volume=0.08",
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                    str(output),
                ], check=True)
            chunks = [
                chunk(
                    "intro__001",
                    segment_id="intro",
                    segment_kind="intro",
                    beat_id="intro__beat_001",
                    beat_index=1,
                    audio_path="segments/first.wav",
                    audio_sha256=file_sha256(first_audio),
                    duration=3.0,
                    last_in_beat=True,
                    last_in_segment=True,
                ),
                chunk(
                    "outro__001",
                    segment_id="outro",
                    segment_kind="outro",
                    beat_id="outro__beat_001",
                    beat_index=1,
                    audio_path="segments/second.wav",
                    audio_sha256=file_sha256(second_audio),
                    duration=3.0,
                    last_in_beat=True,
                    last_in_segment=True,
                ),
            ]
            state = completed_state(chunks)
            pause_map_path = root / "narration-pause-map.json"
            pause_map = build_pause_map(state, output_path=pause_map_path)
            report = mix_compilation_audio(
                state,
                artifact_root=root,
                pause_map=pause_map,
                pause_map_path=pause_map_path,
            )

            self.assertTrue((root / "compilation_voice_mix.wav").is_file())
            self.assertTrue((root / "audio-mix-report.json").is_file())
            self.assertTrue(
                verify_self_hash(report, "audio_mix_report_sha256"),
            )
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["loudness"]["integrated_loudness_pass"])
            self.assertTrue(report["loudness"]["true_peak_pass"])
            self.assertFalse(report["network_used"])
            self.assertFalse(report["publication_authorized"])


if __name__ == "__main__":
    unittest.main()
