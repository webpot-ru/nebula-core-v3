import tempfile
import unittest
from pathlib import Path

from scripts.render_emotion_video_sample import (
    ass_time, caption_chunks, estimated_words, write_ass, write_reddit_pages_ass,
)


class EmotionVideoSampleTests(unittest.TestCase):
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
        self.assertNotIn(r"Чанк 0\NЧанк 1", value)
        self.assertIn("Комментарии 438", value)


if __name__ == "__main__":
    unittest.main()
