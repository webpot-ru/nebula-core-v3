import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.configure_ai33_pronunciation_dictionary import DictionarySetupError, configure


def response(payload, status=200):
    value = Mock()
    value.ok = status < 400
    value.status_code = status
    value.json.return_value = payload
    return value


class ConfigureAi33PronunciationDictionaryTests(unittest.TestCase):
    def test_dry_run_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as temp, patch("scripts.configure_ai33_pronunciation_dictionary.requests") as requests:
            result = configure(api_key="", output_path=Path(temp) / "result.json", apply=False)
        self.assertEqual(result["status"], "DRY_RUN")
        requests.get.assert_not_called()
        requests.post.assert_not_called()

    def test_create_and_readback_exact_dictionary(self):
        rules = [
            {"from": "Chonker Talks", "to": "Чонкер Толкс", "matchType": "contains", "caseSensitive": False},
            {"from": "Reddit", "to": "Реддит", "matchType": "word", "caseSensitive": False},
            {"from": "AITA", "to": "эй ай ти эй", "matchType": "word", "caseSensitive": False},
            {"from": "AMA", "to": "эй эм эй", "matchType": "word", "caseSensitive": False},
        ]
        created = {"id": 17, "name": "Chonker Talks RU v1", "rules": rules}
        with tempfile.TemporaryDirectory() as temp, \
             patch("scripts.configure_ai33_pronunciation_dictionary.requests.get", side_effect=[
                 response({"success": True, "dictionaries": []}),
                 response({"success": True, "dictionary": created}),
             ]), \
             patch("scripts.configure_ai33_pronunciation_dictionary.requests.post", return_value=response({"success": True, "dictionary": created})):
            result = configure(api_key="secret", output_path=Path(temp) / "result.json", apply=True)
        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(result["dictionary_id"], 17)

    def test_same_name_with_different_rules_fails_before_create(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch("scripts.configure_ai33_pronunciation_dictionary.requests.get", return_value=response({
                 "success": True,
                 "dictionaries": [{"id": 8, "name": "Chonker Talks RU v1", "rules": []}],
             })), \
             patch("scripts.configure_ai33_pronunciation_dictionary.requests.post") as post:
            with self.assertRaisesRegex(DictionarySetupError, "different rules"):
                configure(api_key="secret", output_path=Path(temp) / "result.json", apply=True)
        post.assert_not_called()
