import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.render_emotion_video_sample import (
    ass_time, caption_chunks, estimated_words, fixed_wrapped_prefix, write_ass,
    write_reddit_pages_ass,
    render,
)


class EmotionVideoSampleTests(unittest.TestCase):
    @patch("scripts.render_emotion_video_sample.subprocess.run")
    @patch("scripts.render_emotion_video_sample.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_video_background_loops_and_ignores_its_audio(self, _which, run):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            render(root / "loop.mp4", root / "voice.mp3", root / "captions.ass",
                   root / "out.mp4", 12.0)
        command = run.call_args.args[0]
        self.assertIn("-stream_loop", command)
        self.assertNotIn("-loop", command)
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertEqual(command[command.index("-map", command.index("-map") + 1) + 1], "1:a:0")

    def test_tags_are_not_visible_and_captions_are_chunked(self):
        words = estimated_words("[whispers] Это короткая эмоциональная фраза для проверки синхронизации текста.", 8.0)
        chunks = caption_chunks(words, max_words=4, max_chars=30)
        self.assertGreater(len(chunks), 1)
        self.assertNotIn("whispers", " ".join(item["text"] for item in chunks))
        self.assertEqual(chunks[0]["start"], 0.0)

    def test_caption_chunks_prefer_phrase_punctuation(self):
        words = estimated_words("Я почти смеялся над ними, пока часы не показали три пятнадцать.", 7.0)
        chunks = caption_chunks(words)
        self.assertEqual([item["text"] for item in chunks], [
            "Я почти смеялся над ними,", "пока часы не показали три пятнадцать.",
        ])

    def test_ass_output_is_timed_and_escaped(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "captions.ass"
            write_ass([{"start": 1.25, "end": 3.5, "text": "Фраза {один}"}], path)
            value = path.read_text()
        self.assertIn("0:00:01.25", value)
        self.assertIn(r"\{один\}", value)
        self.assertEqual(ass_time(65.5), "0:01:05.50")

    def test_reddit_pages_accumulate_one_paragraph_without_repeating_title(self):
        chunks = [{"start": index * 2.0, "end": index * 2.0 + 1.5, "text": f"Чанк {index}"} for index in range(7)]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reddit.ass"
            write_reddit_pages_ass(chunks, path, duration=16.0, title="Заголовок",
                                   first_page_chars=40, continuation_page_chars=40)
            value = path.read_text()
        self.assertEqual(value.count("Заголовок"), 1)
        self.assertEqual(value.count("Style: Body"), 1)
        self.assertEqual(value.count("Dialogue: 0"), 9)
        self.assertIn("Чанк 0 Чанк 1", value)
        self.assertIn("Ответить", value)
        self.assertIn("Поделиться", value)
        self.assertIn(r"\p1", value)
        self.assertIn(r"\pos(86,972)", value)
        self.assertNotIn(r"\\N", value)
        self.assertNotIn("▲", value)
        self.assertNotIn(r"\fad(90,0)", value)
        self.assertIn("Style: Body,Reddit Sans,40", value)
        self.assertNotIn("Сохранить", value)
        self.assertIn("Dialogue: 3,0:00:12.80,0:00:16.00,OutlineIcon", value)

    def test_fixed_wrapping_does_not_move_existing_words(self):
        full = "Один два три четыре пять шесть семь восемь девять десять"
        early = fixed_wrapped_prefix(full, "Один два три четыре", line_chars=20)
        later = fixed_wrapped_prefix(full, "Один два три четыре пять шесть", line_chars=20)
        self.assertEqual(early.split(r"\N")[0], later.split(r"\N")[0])
        self.assertEqual(early, "Один два три четыре")
        self.assertTrue(later.startswith(early + r"\N"))

    def test_short_sample_stays_on_one_dense_reddit_page(self):
        chunks = [
            {"start": index * 2.0, "end": index * 2.0 + 1.5,
             "text": "Ночная смена продолжалась и правило становилось всё страшнее"}
            for index in range(6)
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dense.ass"
            write_reddit_pages_ass(chunks, path, duration=14.0, title="Заголовок")
            value = path.read_text()
        self.assertEqual(value.count("Заголовок"), 1)
        self.assertEqual(value.count("u/anonymous"), 1)
        self.assertIn(r"\N", value)
        self.assertNotIn(r"\pos(80,90)", value)


if __name__ == "__main__":
    unittest.main()
