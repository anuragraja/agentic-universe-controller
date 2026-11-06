"""Unit tests for controller.storage."""
import tempfile
import unittest
from pathlib import Path

from controller.storage import Storage


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        Path(self.db_path).unlink(missing_ok=True)

    def test_state_roundtrip(self):
        self.assertIsNone(self.storage.get_state("foo"))
        self.storage.set_state("foo", {"bar": 123})
        self.assertEqual(self.storage.get_state("foo"), {"bar": 123})

    def test_leads_and_chunk_watermark(self):
        self.assertFalse(self.storage.is_chunk_ingested(1))
        self.storage.record_chunk_ingested(1, "events", 100, 1, 100)
        self.assertTrue(self.storage.is_chunk_ingested(1))
        self.assertEqual(self.storage.get_last_chunk_id(), 1)

        leads = [
            ("l1", "p1", "wf1", "c1", "hi", "1", "18-30", "mid"),
            ("l2", "p2", "wf1", "c1", "en", "2", "60+", "high"),
        ]
        self.storage.insert_leads_batch(leads)
        lead = self.storage.get_lead("l1")
        self.assertIsNotNone(lead)
        self.assertEqual(lead["lang"], "hi")

    def test_call_stats_and_queries(self):
        # (workflow_id, cohort_id, welcome, voice, caller_id, prompt_version, dials, conn, eng, halluc)
        rows = [
            ("wf1", "senior", "W1", "V1", "D1", "P1", 10, 5, 3, 0),
            ("wf1", "senior", "W1", "V2", "D1", "P1", 10, 6, 4, 1),
        ]
        self.storage.update_call_stats_batch(rows)
        voice_stats = self.storage.get_cohort_dim_stats("wf1", "senior", "voice")
        self.assertIn("V1", voice_stats)
        self.assertIn("V2", voice_stats)
        self.assertEqual(voice_stats["V1"]["connected"], 5)
        self.assertEqual(voice_stats["V1"]["engaged"], 3)
        self.assertEqual(voice_stats["V2"]["engaged"], 4)

    def test_proposals_and_audit(self):
        prop = {
            "proposal_id": "p_001",
            "workflow_id": "wf1",
            "base_version": 1,
            "proposed_config": {"allocations": {}},
            "change_summary": "test voice update",
            "diff": {"voice": "V2"},
            "affected_leads": 500,
            "dry_run": {"estimated_lift": 0.05},
            "impact_score": 0.45,
            "rationale": "V2 has higher engagement in history",
            "evidence": None,
            "status": "pending",
            "created_minute": 600,
        }
        self.storage.save_proposal(prop)
        ret = self.storage.get_proposal("p_001")
        self.assertEqual(ret["status"], "pending")
        self.assertEqual(ret["impact_score"], 0.45)

        self.storage.update_proposal_status("p_001", "approved", approval_id="apr_123")
        ret2 = self.storage.get_proposal("p_001")
        self.assertEqual(ret2["status"], "approved")
        self.assertEqual(ret2["approval_id"], "apr_123")

        self.storage.log_audit(
            sim_minute=600,
            ts="2027-01-04T10:00:00+05:30",
            workflow_id="wf1",
            actor="controller",
            action="proposal_created",
            summary="Submitted proposal for voice update",
            version=1,
            details={"proposal_id": "p_001"},
        )
        logs = self.storage.query_audit_trail("wf1")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "proposal_created")


if __name__ == "__main__":
    unittest.main()
