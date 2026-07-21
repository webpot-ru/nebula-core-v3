import os
import unittest
from unittest.mock import patch

from acc1_pronunciation_dictionary import (
    PronunciationDictionaryError,
    load_acc1_pronunciation_dictionary,
    preview_pronunciation,
    resolve_acc1_pronunciation_dictionary_id,
)


class Acc1PronunciationDictionaryTests(unittest.TestCase):
    def test_spec_is_valid_and_checksum_bound(self):
        spec = load_acc1_pronunciation_dictionary()
        self.assertEqual(spec["channel"], "acc1")
        self.assertRegex(spec["sha256"], r"^[0-9a-f]{64}$")

    def test_preview_applies_word_and_contains_rules(self):
        spec = load_acc1_pronunciation_dictionary()
        self.assertEqual(
            preview_pronunciation("Chonker Talks читает Reddit и AITA.", spec["rules"]),
            "Чонкер Толкс читает Реддит и эй ай ти эй.",
        )

    def test_remote_id_is_required_and_positive(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PronunciationDictionaryError, "is required"):
                resolve_acc1_pronunciation_dictionary_id(required=True)
        with patch.dict(os.environ, {"AI33_PRONUNCIATION_DICTIONARY_ID": "17"}, clear=True):
            self.assertEqual(resolve_acc1_pronunciation_dictionary_id(required=True), 17)
        with patch.dict(os.environ, {"AI33_PRONUNCIATION_DICTIONARY_ID": "0"}, clear=True):
            with self.assertRaisesRegex(PronunciationDictionaryError, "positive integer"):
                resolve_acc1_pronunciation_dictionary_id(required=True)
