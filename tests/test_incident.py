"""Unit tests for controller.incident."""
import unittest

from controller.incident import IncidentManager


class DummyResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class DummyHttpClient:
    def post(self, path: str, json: dict):
        if path == "/llm/suggest-fixes":
            return DummyResponse(200, {"suggestions": [{"prompt_version": "P3"}, {"prompt_version": "P5"}]})
        elif path == "/validation/runs":
            pv = json["prompt_version"]
            rate = 0.995 if pv == "P3" else 0.94
            return DummyResponse(200, {"validation_run_id": f"val_{pv}", "pass_rate": rate})
        return DummyResponse(404, {})


class TestIncident(unittest.TestCase):
    def test_hallucination_detection(self):
        mgr = IncidentManager(flag_threshold=0.03, min_calls=100)

        # Clean prompt: 1 flag in 100 calls (1%) -> no incident
        clean_stats = {"connected": 100, "halluc_flags": 1}
        is_inc, est_h, _ = mgr.check_hallucination_incident("P1", clean_stats)
        self.assertFalse(is_inc)
        self.assertLess(est_h, 0.01)

        # Spiking prompt: 6 flags in 100 calls (6%) -> incident!
        bad_stats = {"connected": 100, "halluc_flags": 6}
        is_inc2, est_h2, summary = mgr.check_hallucination_incident("P2", bad_stats)
        self.assertTrue(is_inc2)
        self.assertGreaterEqual(est_h2, 0.05)
        self.assertIn("ALERT", summary)

    def test_select_best_fix(self):
        mgr = IncidentManager()
        client = DummyHttpClient()
        res = mgr.select_best_fix("wf1", "P2", ["P1", "P2", "P3", "P5"], client, 0.97)
        self.assertIsNotNone(res)
        cand, run_id, rate = res
        self.assertEqual(cand, "P3")
        self.assertEqual(run_id, "val_P3")
        self.assertGreaterEqual(rate, 0.97)


if __name__ == "__main__":
    unittest.main()
