import tempfile
import unittest
from pathlib import Path

from reddit_media import RedditMediaError, download_media_assets


class FakeResponse:
    status_code = 200
    headers = {"Content-Type": "image/png"}
    def iter_content(self, _size):
        yield b"\x89PNG\r\n\x1a\nfixture"


class FakeSession:
    def get(self, *_args, **_kwargs):
        return FakeResponse()


class RedditMediaDownloadTests(unittest.TestCase):
    def test_downloads_allowed_static_image_with_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            result = download_media_assets(
                [{"media_id": "one", "source_url": "https://i.redd.it/one.png", "width": 10, "height": 10}],
                Path(temp),
                session=FakeSession(),
            )
            self.assertEqual(result[0]["download_status"], "verified")
            self.assertTrue(Path(result[0]["local_path"]).is_file())
            self.assertEqual(len(result[0]["sha256"]), 64)

    def test_rejects_arbitrary_external_host(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RedditMediaError):
                download_media_assets([{"media_id": "x", "source_url": "https://example.com/x.png"}], Path(temp), session=FakeSession())


if __name__ == "__main__":
    unittest.main()
