import unittest

from acc1_narration_profiles import (
    NARRATION_PROFILES,
    NARRATION_PROFILES_SHA256,
    NARRATION_PROFILE_IDS_BY_PILLAR,
    NarrationProfileError,
    canonical_hash,
    profile_payload,
    resolve_narration_boundary_contract,
    resolve_narration_profile,
    verify_narration_boundary_contract,
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

    def test_format_boundary_contracts_are_checksum_bound_and_distinct(self):
        profile = resolve_narration_profile(
            NARRATION_PROFILE_IDS_BY_PILLAR["relationships_family"],
            pillar_id="relationships_family",
        )
        bundle = resolve_narration_boundary_contract(
            profile,
            episode_format="BUNDLE",
            source_count=3,
        )
        saga = resolve_narration_boundary_contract(
            profile,
            episode_format="SAGA",
            source_count=1,
        )
        thread = resolve_narration_boundary_contract(
            profile,
            episode_format="THREAD",
            source_count=4,
        )
        self.assertTrue(verify_narration_boundary_contract(bundle))
        self.assertTrue(verify_narration_boundary_contract(saga))
        self.assertTrue(verify_narration_boundary_contract(thread))
        self.assertEqual(bundle["spoken_transition_count"], 2)
        self.assertLess(
            bundle["effective_transition_speed"],
            bundle["base_speed"],
        )
        self.assertEqual(
            bundle["pause_before_announcement_sec"],
            profile["pause_after"]["segment_seconds"]["story"],
        )
        self.assertEqual(
            bundle["pause_after_announcement_sec"],
            profile["pause_after"]["segment_seconds"]["transition"],
        )
        self.assertEqual(saga["spoken_transition_count"], 0)
        self.assertEqual(thread["spoken_transition_count"], 0)
        self.assertTrue(thread["distinct_comment_voice_required"])

    def test_boundary_contract_rejects_wrong_format_counts(self):
        profile = resolve_narration_profile(
            NARRATION_PROFILE_IDS_BY_PILLAR["relationships_family"],
            pillar_id="relationships_family",
        )
        with self.assertRaisesRegex(NarrationProfileError, "at least two"):
            resolve_narration_boundary_contract(
                profile,
                episode_format="BUNDLE",
                source_count=1,
            )
        with self.assertRaisesRegex(NarrationProfileError, "exactly one"):
            resolve_narration_boundary_contract(
                profile,
                episode_format="SAGA",
                source_count=2,
            )


if __name__ == "__main__":
    unittest.main()
