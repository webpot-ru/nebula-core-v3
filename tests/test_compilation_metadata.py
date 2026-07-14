import unittest

from compilation_metadata import CompilationMetadataError, accepted_story_summary, validate_metadata


def compilation():
    return {"stories": [{
        "title_ru": f"История {index}",
        "editorial_review": {"verdict": "PASS"},
        "ending_preserved_evidence": "ending",
        "source_snapshot": {"post_id": str(index), "title": f"Story {index}", "truth_mode": "fiction", "source_url": f"https://reddit/{index}"},
    } for index in range(1, 4)]}


class CompilationMetadataTests(unittest.TestCase):
    def test_requires_all_stories_to_pass(self):
        value = compilation()
        value["stories"][0]["editorial_review"]["verdict"] = "REVISE"
        with self.assertRaises(CompilationMetadataError):
            accepted_story_summary(value)

    def test_accepts_three_distinct_options_and_all_urls(self):
        value = compilation()
        payload = {
            "packaging_options": [
                {"youtube_title": f"Title {i}", "thumbnail_text": f"Text {i}", "angle": f"angle-{i}"}
                for i in range(3)
            ],
            "youtube_description": " ".join(f"https://reddit/{i}" for i in range(1, 4)),
            "language": "ru",
        }
        self.assertEqual(validate_metadata(payload, value), [])


if __name__ == "__main__":
    unittest.main()
