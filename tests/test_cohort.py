"""Unit tests for controller.cohort."""
import unittest

from controller.cohort import classify_lead, count_cohort_breakdown, validate_cohorts, propose_standard_cohorts


class TestCohort(unittest.TestCase):
    def test_classify_and_order(self):
        cohorts = [
            {"id": "senior_ta", "where": {"age_band": ["60+"], "lang": ["ta"]}},
            {"id": "seniors", "where": {"age_band": ["60+"]}},
            {"id": "young", "where": {"age_band": ["18-30"]}},
        ]
        # Matches first
        l1 = {"age_band": "60+", "lang": "ta", "city_tier": "1", "value_band": "high"}
        self.assertEqual(classify_lead(l1, cohorts), "senior_ta")

        # Matches second
        l2 = {"age_band": "60+", "lang": "hi", "city_tier": "1", "value_band": "high"}
        self.assertEqual(classify_lead(l2, cohorts), "seniors")

        # Matches third
        l3 = {"age_band": "18-30", "lang": "en", "city_tier": "2", "value_band": "low"}
        self.assertEqual(classify_lead(l3, cohorts), "young")

        # Fallback to default
        l4 = {"age_band": "31-45", "lang": "hi", "city_tier": "1", "value_band": "mid"}
        self.assertEqual(classify_lead(l4, cohorts), "default")

    def test_validation(self):
        bad_cohorts = [
            {"id": "default", "where": {}},
            {"id": "valid_1", "where": {"unknown_feat": ["1"]}},
            {"id": "valid_2", "where": {"lang": ["martian"]}},
        ]
        probs = validate_cohorts(bad_cohorts)
        self.assertGreaterEqual(len(probs), 3)

        good_cohorts = propose_standard_cohorts("nw_renewal", ["hi", "en", "ta"])
        self.assertEqual(validate_cohorts(good_cohorts), [])


if __name__ == "__main__":
    unittest.main()

