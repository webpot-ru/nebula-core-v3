import unittest
from types import SimpleNamespace

import scraper


class RedditMediaManifestTests(unittest.TestCase):
    def test_never_triggers_lazy_praw_fetch_for_missing_media_fields(self):
        class ListingSubmission:
            def __init__(self):
                self.id = "listing-only"
                self.title = "Hydrated listing row"

            def __getattr__(self, name):
                raise AssertionError(f"lazy fetch attempted for {name}")

        self.assertEqual(scraper.reddit_media_manifest(ListingSubmission()), [])

    def test_extracts_ordered_static_gallery_and_unescapes_url(self):
        post = SimpleNamespace(
            id="gallery",
            gallery_data={"items": [
                {"media_id": "second", "caption": "Second"},
                {"media_id": "first", "caption": "First"},
            ]},
            media_metadata={
                "first": {"status": "valid", "e": "Image", "s": {"u": "https://i.redd.it/first.jpg", "x": 800, "y": 600}},
                "second": {"status": "valid", "e": "Image", "s": {"u": "https://preview.redd.it/second.jpg?x=1&amp;y=2", "x": 1200, "y": 900}},
            },
        )
        assets = scraper.reddit_media_manifest(post)
        self.assertEqual([item["media_id"] for item in assets], ["second", "first"])
        self.assertIn("&y=2", assets[0]["source_url"])

    def test_rejects_external_and_animated_media(self):
        external = SimpleNamespace(
            id="external", gallery_data={}, media_metadata={}, preview={},
            post_hint="image", url="https://example.com/image.jpg",
        )
        self.assertEqual(scraper.reddit_media_manifest(external), [])
        animated = SimpleNamespace(
            id="animated",
            gallery_data={"items": [{"media_id": "gif"}]},
            media_metadata={"gif": {"status": "valid", "e": "AnimatedImage", "s": {"u": "https://i.redd.it/a.gif"}}},
            preview={},
        )
        self.assertEqual(scraper.reddit_media_manifest(animated), [])

    def test_extracts_native_preview_image(self):
        post = SimpleNamespace(
            id="one", gallery_data={}, media_metadata={},
            preview={"images": [{"source": {"url": "https://preview.redd.it/one.png", "width": 640, "height": 480}}]},
        )
        assets = scraper.reddit_media_manifest(post)
        self.assertEqual(assets[0]["width"], 640)
        self.assertTrue(assets[0]["reddit_hosted"])


if __name__ == "__main__":
    unittest.main()
