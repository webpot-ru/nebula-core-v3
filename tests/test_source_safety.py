import unittest

from source_safety import source_safety_evidence


class SourceSafetyTests(unittest.TestCase):
    def test_normal_personal_account_passes(self):
        report = source_safety_evidence(
            {},
            "I changed jobs after the argument, spoke to my manager, and moved on.",
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["matched_source_flags"], [])
        self.assertEqual(report["matched_blocker_ids"], [])

    def test_explicit_source_flag_blocks(self):
        report = source_safety_evidence(
            {"contains_doxxing": True},
            "The rest of the account contains ordinary prose.",
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["matched_source_flags"], ["contains_doxxing"])

    def test_email_and_phone_are_high_confidence_pii_blocks(self):
        report = source_safety_evidence(
            {},
            "Contact the person at private.person@example.com or +1 (212) 555-0199.",
        )
        self.assertFalse(report["passed"])
        self.assertEqual(
            report["matched_blocker_ids"],
            ["email_address", "phone_number"],
        )

    def test_high_confidence_wrongdoing_instructions_block(self):
        report = source_safety_evidence(
            {},
            "Here is a step-by-step guide to make an explosive device.",
        )
        self.assertFalse(report["passed"])
        self.assertIn("high_confidence_pattern_1", report["matched_blocker_ids"])


if __name__ == "__main__":
    unittest.main()
