"""Unit tests for controller.governance."""
import tempfile
import unittest
from pathlib import Path

from controller.governance import GovernanceClient
from controller.storage import Storage


class DummyHttpResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class MockHttpClient:
    def __init__(self):
        self.approvals = {}

    def post(self, path: str, json: dict):
        if path == "/approvals":
            aid = f"apr_{len(self.approvals) + 1:03d}"
            self.approvals[aid] = {"status": "approved", "approval_id": aid}
            return DummyHttpResponse(200, {"approval_id": aid, "status": "pending"})
        elif path.endswith("/apply"):
            return DummyHttpResponse(200, {"version": 2, "changed_dims": ["voice"]})
        return DummyHttpResponse(404, {})

    def put(self, path: str, json: dict):
        return DummyHttpResponse(200, {"version": 3, "changed_dims": ["caller_id"]})

    def get(self, path: str):
        aid = path.split("/")[-1]
        return DummyHttpResponse(200, self.approvals.get(aid, {"status": "pending"}))


class TestGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.storage = Storage(self.db_path)
        self.http = MockHttpClient()
        self.gov = GovernanceClient(self.http, self.storage)

    def tearDown(self):
        self.storage.close()
        Path(self.db_path).unlink(missing_ok=True)

    def test_working_hour(self):
        # 10:00 AM is minute 600 -> True
        self.assertTrue(self.gov.is_working_hour(600, [10, 19]))
        # 8:00 AM is minute 480 -> False
        self.assertFalse(self.gov.is_working_hour(480, [10, 19]))

    def test_auto_apply_policy(self):
        pol = {"auto_apply": {"enabled": True, "allowed_dims": ["caller_id", "schedule"], "max_shift": 0.5}}
        can, shift, msg = self.gov.can_auto_apply(
            {"allocations": {"default": {"caller_id": {"D1": 1.0}}}},
            {"allocations": {"default": {"caller_id": {"D1": 0.5, "D2": 0.5}}}},
            ["caller_id"],
            pol,
        )
        self.assertTrue(can)
        self.assertAlmostEqual(shift, 0.5)

        # Disallowed dimension (voice)
        can2, _, _ = self.gov.can_auto_apply({}, {}, ["voice"], pol)
        self.assertFalse(can2)

    def test_proposal_lifecycle(self):
        aid = self.gov.submit_proposal(
            workflow_id="wf1",
            base_version=1,
            current_config={"allocations": {"default": {"voice": {"V1": 1.0}}}},
            proposed_config={"allocations": {"default": {"voice": {"V2": 1.0}}}},
            change_summary="Update voice",
            rationale="V2 superior",
            affected_leads=500,
            dry_run={"lift": 0.05},
            impact_score=0.4,
            sim_minute=660,
            sim_ts="2027-01-04T11:00:00+05:30",
        )
        self.assertIsNotNone(aid)
        prop = self.storage.get_proposal(self.storage.get_pending_proposals()[0]["proposal_id"])
        self.assertEqual(prop["status"], "pending")

        # Reconcile -> apply
        self.gov.reconcile_pending_approvals(690, "2027-01-04T11:30:00+05:30")
        prop_after = self.storage.get_proposal(prop["proposal_id"])
        self.assertEqual(prop_after["status"], "applied")
        self.assertEqual(prop_after["applied_version"], 2)


if __name__ == "__main__":
    unittest.main()
