from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acc1_caption_burn import (
    CaptionBurnError,
    burn_captions,
    subtitle_filter,
    write_caption_ass,
)


class CaptionBurnTest(unittest.TestCase):
    def test_ass_pins_one_line_to_the_fixed_1080p_band(self):
        track = {
            "cues": [
                {
                    "start_sec": 1.0,
                    "end_sec": 2.5,
                    "text": "Субтитр в середине нижней полосы",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            output = write_caption_ass(track, Path(temp) / "captions.ass")
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1920", rendered)
        self.assertIn("PlayResY: 1080", rendered)
        self.assertIn("WrapStyle: 2", rendered)
        self.assertIn("Style: Caption,Arial,42", rendered)
        self.assertIn(",2,70,70,38,1", rendered)
        self.assertIn(r"{\q2}Субтитр в середине нижней полосы", rendered)
        self.assertEqual(subtitle_filter(Path("captions.ass")), "ass=filename='captions.ass'")

    def test_ass_rejects_overlapping_cues(self):
        track = {
            "cues": [
                {"start_sec": 1.0, "end_sec": 3.0, "text": "Первая"},
                {"start_sec": 2.0, "end_sec": 4.0, "text": "Вторая"},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(CaptionBurnError):
                write_caption_ass(track, Path(temp) / "captions.ass")

    @patch("acc1_caption_burn.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("acc1_caption_burn.subprocess.run")
    def test_burn_reencodes_video_and_copies_audio(self, run, _which):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            captions = root / "captions.ass"
            output = root / "output.mp4"
            source.write_bytes(b"source")
            captions.write_text("[Events]\n", encoding="utf-8")

            def materialize(command, **_kwargs):
                Path(command[-1]).write_bytes(b"captioned")

            run.side_effect = materialize
            burn_captions(source, captions, output)
            command = run.call_args.args[0]
        self.assertIn("libx264", command)
        self.assertIn("copy", command)
        self.assertIn("ass=filename='captions.ass'", command)

    @patch("acc1_caption_burn.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("acc1_caption_burn.subprocess.run")
    def test_burn_normalizes_segmented_video_to_exact_frame_count(
        self,
        run,
        _which,
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            captions = root / "captions.ass"
            output = root / "output.mp4"
            source.write_bytes(b"source")
            captions.write_text("[Events]\n", encoding="utf-8")

            def materialize(command, **_kwargs):
                Path(command[-1]).write_bytes(b"captioned")

            run.side_effect = materialize
            burn_captions(
                source,
                captions,
                output,
                target_duration_sec=10.018,
                fps=30,
            )
            command = run.call_args.args[0]
            video_filter = command[command.index("-vf") + 1]
        self.assertIn("fps=30", video_filter)
        self.assertIn("tpad=stop_mode=clone:stop_duration=10.033333", video_filter)
        self.assertIn("trim=end_frame=301", video_filter)
        self.assertIn("setpts=N/(30*TB)", video_filter)
        self.assertEqual(command[command.index("-frames:v") + 1], "301")
        self.assertEqual(command[command.index("-t") + 1], "10.033333")

    def test_burn_rejects_partial_duration_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(
                CaptionBurnError,
                "must be supplied together",
            ):
                burn_captions(
                    root / "source.mp4",
                    root / "captions.ass",
                    root / "output.mp4",
                    target_duration_sec=10.0,
                )


if __name__ == "__main__":
    unittest.main()
