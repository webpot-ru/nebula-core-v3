import unittest

from acc1_narration_profiles import (
    NARRATION_PROFILES,
    NARRATION_PROFILES_SHA256,
    NARRATION_PROFILE_IDS_BY_PILLAR,
    NarrationProfileError,
    canonical_hash,
    profile_payload,
    resolve_narration_profile,
    verify_narration_profile,
)


class Acc1NarrationProfileTests(unittest.TestCase):
    def test_five_pillars_have_checksum_bound_profiles_without_voice_ids(self):
        self.assertEqual(len(NARRATION_PROFILE_IDS_BY_PILLAR), 5)
        self.assertEqual(len(NARRATION_PROFILES), 5)
        for pillar_id, profile_id in NARRATION_PROFILE_IDS_BY_PILLAR.items():
            profile = resolve_narration_profile(
                profile_id, pillar_id=pillar_id,
            )
            self.assertTrue(verify_narration_profile(profile))
            self.assertEqual(
                profile["profile_sha256"],
                canonical_hash(profile_payload(profile)),
            )
            self.assertNotIn("voice_id", profile)
            self.assertNotIn("comment_voice_id", profile)
            self.assertEqual(profile["voice_only_loudness"], {
                "integrated_lufs": -16.0,
                "tolerance_lu": 1.0,
                "max_true_peak_dbtp": -1.5,
            })
        self.assertRegex(NARRATION_PROFILES_SHA256, r"^[0-9a-f]{64}$")

    def test_unknown_or_cross_pillar_profile_fails_closed(self):
        with self.assertRaisesRegex(NarrationProfileError, "pillar must be"):
            resolve_narration_profile(
                next(iter(NARRATION_PROFILES)), pillar_id="unknown",
            )
        with self.assertRaisesRegex(NarrationProfileError, "must be one of"):
            resolve_narration_profile(
                "unknown_profile", pillar_id="relationships_family",
            )
        wrong = NARRATION_PROFILE_IDS_BY_PILLAR["work_money_justice"]
        with self.assertRaisesRegex(NarrationProfileError, "does not match pillar"):
            resolve_narration_profile(
                wrong, pillar_id="relationships_family",
            )


if __name__ == "__main__":
    unittest.main()
