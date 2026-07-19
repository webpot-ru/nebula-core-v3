import unittest

from acc1_language_gate import is_russian_text, russian_text_evidence


class Acc1LanguageGateTests(unittest.TestCase):
    def test_russian_prose_and_brand_mix_pass(self):
        self.assertTrue(is_russian_text("Полная русская история с понятной развязкой", minimum_cyrillic_words=3))
        self.assertTrue(is_russian_text(
            "Chonker Talks — истории Reddit на русском",
            minimum_cyrillic_words=2,
            minimum_cyrillic_letter_ratio=0.40,
        ))

    def test_english_echo_and_language_label_only_fail(self):
        self.assertFalse(is_russian_text("This is the unchanged English source story"))
        evidence = russian_text_evidence("ru: complete English narration")
        self.assertFalse(evidence["passed"])
        self.assertLess(evidence["cyrillic_letter_ratio"], 0.60)


if __name__ == "__main__":
    unittest.main()
