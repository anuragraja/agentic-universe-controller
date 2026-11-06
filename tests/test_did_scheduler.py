"""Unit tests for did_manager and scheduler."""
import unittest

from controller.did_manager import DidManager
from controller.scheduler import build_hour_weights, extract_lead_preferred_hours


class TestDidAndScheduler(unittest.TestCase):
    def test_did_degradation_detection(self):
        mgr = DidManager(min_sample=50, degradation_ratio=0.65)
        stats = {
            "D1": {"dials": 100, "connected": 40},  # 40%
            "D2": {"dials": 100, "connected": 12},  # 12% (degraded)
            "D3": {"dials": 100, "connected": 38},  # 38%
        }
        alloc, degraded, rationale = mgr.recommend_caller_id_allocation(
            options=["D1", "D2", "D3"],
            stats=stats,
            current_alloc={"D1": 0.5, "D2": 0.5},
        )
        self.assertIn("D2", degraded)
        self.assertNotIn("D2", alloc)
        self.assertIn("D1", alloc)
        self.assertIn("D3", alloc)
        self.assertAlmostEqual(sum(alloc.values()), 1.0)

    def test_build_hour_weights(self):
        cohorts = [
            {"id": "seniors", "where": {"age_band": ["60+"]}},
            {"id": "young", "where": {"age_band": ["18-30"]}},
        ]
        hw = build_hour_weights((9, 21), cohorts)
        self.assertIn("default", hw)
        self.assertIn("seniors", hw)
        self.assertIn("young", hw)

        # Check all hours present
        for h in range(9, 21):
            self.assertIn(str(h), hw["default"])
            self.assertIn(str(h), hw["seniors"])
            self.assertIn(str(h), hw["young"])

        # Seniors peak at 10 AM, young at 18 (6 PM)
        self.assertGreater(hw["seniors"]["10"], hw["seniors"]["18"])
        self.assertGreater(hw["young"]["18"], hw["young"]["10"])

    def test_preferred_hours(self):
        rows = [
            ("p1", 10, 2, 2),
            ("p1", 14, 2, 1),
            ("p2", 18, 3, 3),
        ]
        pref = extract_lead_preferred_hours(rows, (9, 21))
        self.assertEqual(pref["p1"], 10)
        self.assertEqual(pref["p2"], 18)


if __name__ == "__main__":
    unittest.main()
