"""Unit tests for controller.stats."""
import unittest

from controller.stats import (
    beta_posterior,
    prob_b_greater_than_a,
    calculate_tvd,
    max_allocation_shift,
    ExperimentAnalyzer,
)


class TestStats(unittest.TestCase):
    def test_beta_posterior(self):
        a, b, mean, var = beta_posterior(50, 100)
        self.assertEqual(a, 51.0)
        self.assertEqual(b, 51.0)
        self.assertAlmostEqual(mean, 0.5)

    def test_prob_b_greater_than_a(self):
        # A: 40/100 (40%), B: 70/100 (70%) -> B should be vastly superior
        p = prob_b_greater_than_a(40, 100, 70, 100)
        self.assertGreater(p, 0.99)

        # Equal: 50/100 vs 50/100 -> ~0.5
        p_eq = prob_b_greater_than_a(50, 100, 50, 100)
        self.assertAlmostEqual(p_eq, 0.5, places=2)

    def test_tvd_and_shift(self):
        d1 = {"V1": 1.0}
        d2 = {"V1": 0.8, "V2": 0.2}
        tvd = calculate_tvd(d1, d2)
        self.assertAlmostEqual(tvd, 0.2)

        old_alloc = {"default": {"voice": {"V1": 1.0}, "welcome_message": {"W1": 1.0}}}
        new_alloc = {"default": {"voice": {"V1": 0.7, "V2": 0.3}, "welcome_message": {"W1": 1.0}}}
        shift = max_allocation_shift(old_alloc, new_alloc, ["voice", "welcome_message"])
        self.assertAlmostEqual(shift, 0.3)

    def test_analyzer_and_decay(self):
        analyzer = ExperimentAnalyzer(min_sample_size=100)
        stats = {
            "V1": {"dials": 300, "connected": 200, "engaged": 80},   # 40%
            "V2": {"dials": 300, "connected": 200, "engaged": 120},  # 60%
        }
        res = analyzer.evaluate_dimension(
            dim="voice",
            stats=stats,
            current_alloc={"V1": 1.0},
            options=["V1", "V2"],
            primary_kpi="engagement_rate",
        )
        self.assertTrue(res["is_significant"])
        self.assertEqual(res["winner"], "V2")

        # Test decay detection
        cum_stats = {"dials": 1000, "connected": 800, "engaged": 480}  # 60%
        recent_stats = {"dials": 300, "connected": 200, "engaged": 80}  # 40% (decayed)
        decayed = analyzer.detect_decay("V2", cum_stats, recent_stats, "engagement_rate", drop_threshold=0.1)
        self.assertTrue(decayed)


if __name__ == "__main__":
    unittest.main()

