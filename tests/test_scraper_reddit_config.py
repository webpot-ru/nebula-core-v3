import unittest
from unittest.mock import patch

import scraper


class RedditCredentialConfigTests(unittest.TestCase):
    def test_requires_client_credentials(self):
        with self.assertRaisesRegex(scraper.RedditCredentialConfigError, "REDDIT_CLIENT_ID"):
            scraper.reddit_credentials_from_env({})

    def test_rejects_incomplete_script_pair(self):
        env = {
            "REDDIT_CLIENT_ID": "test-client-id",
            "REDDIT_CLIENT_SECRET": "test-client-secret",
            "REDDIT_USERNAME": "test-user",
        }
        with self.assertRaisesRegex(scraper.RedditCredentialConfigError, "supplied together"):
            scraper.reddit_credentials_from_env(env)

    def test_accepts_read_only_oauth_without_script_pair(self):
        env = {
            "REDDIT_CLIENT_ID": "test-client-id",
            "REDDIT_CLIENT_SECRET": "test-client-secret",
        }
        credentials = scraper.reddit_credentials_from_env(env)
        self.assertEqual(credentials["username"], None)
        self.assertEqual(credentials["password"], None)

    def test_get_reddit_uses_only_explicit_environment_values(self):
        env = {
            "REDDIT_CLIENT_ID": "test-client-id",
            "REDDIT_CLIENT_SECRET": "test-client-secret",
        }

        class FakePraw:
            class Reddit:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs

        with patch.dict("sys.modules", {"praw": FakePraw}):
            with patch.dict("os.environ", env, clear=True):
                client = scraper.get_reddit()

        self.assertEqual(client.kwargs["client_id"], "test-client-id")
        self.assertEqual(client.kwargs["client_secret"], "test-client-secret")
        self.assertNotIn("username", client.kwargs)
        self.assertNotIn("password", client.kwargs)


if __name__ == "__main__":
    unittest.main()
