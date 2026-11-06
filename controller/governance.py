"""Governance client: proposal generation, fatigue limiting, auto-apply, and lifecycle management."""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .stats import max_allocation_shift


class GovernanceClient:
    def __init__(self, http_client: Any, storage: Any):
        self.http = http_client
        self.storage = storage

    def is_working_hour(self, sim_minute: int, approver_hours: List[int]) -> bool:
        lo, hi = approver_hours
        mod = sim_minute % 1440
        hour = mod // 60
        return lo <= hour < hi

    def can_submit_approval(self, workflow_id: str, sim_minute: int, gov_policy: Dict[str, Any]) -> Tuple[bool, str]:
        max_24h = gov_policy.get("max_requests_per_24h", 3)
        recent_count = self.storage.count_proposals_in_last_24h(workflow_id, sim_minute)
        if recent_count >= max_24h:
            return False, f"Fatigue limit reached ({recent_count}/{max_24h} in 24h). Must batch changes."

        # Prefer submitting during working hours to minimize backlog/latency
        approver_hours = gov_policy.get("approver_hours", [10, 19])
        if not self.is_working_hour(sim_minute, approver_hours):
            return False, f"Outside approver working hours [{approver_hours[0]}:00, {approver_hours[1]}:00)."

        return True, "OK"

    def can_auto_apply(
        self,
        current_config: Dict[str, Any],
        proposed_config: Dict[str, Any],
        changed_dims: List[str],
        gov_policy: Dict[str, Any],
    ) -> Tuple[bool, float, str]:
        auto_pol = gov_policy.get("auto_apply", {})
        if not auto_pol.get("enabled", False):
            return False, 0.0, "auto_apply is disabled for this workflow"

        allowed_dims = set(auto_pol.get("allowed_dims", []))
        disallowed = [d for d in changed_dims if d not in allowed_dims]
        if disallowed:
            return False, 0.0, f"Dimensions {disallowed} not permitted for auto_apply"

        max_shift = float(auto_pol.get("max_shift", 0.0))
        agent_dims = [d for d in changed_dims if d in ("welcome_message", "voice", "caller_id")]
        shift = 0.0
        if agent_dims:
            shift = max_allocation_shift(
                current_config.get("allocations", {}),
                proposed_config.get("allocations", {}),
                agent_dims,
            )
            if shift > max_shift + 1e-9:
                return False, shift, f"Shift {shift:.3f} exceeds max_shift {max_shift:.3f}"

        return True, shift, "OK"

    def compute_diff(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        diff = {}
        if old.get("cohorts") != new.get("cohorts"):
            diff["cohorts"] = {"old": old.get("cohorts"), "new": new.get("cohorts")}
        if old.get("prompt_version") != new.get("prompt_version"):
            diff["prompt_version"] = {"old": old.get("prompt_version"), "new": new.get("prompt_version")}
        if old.get("schedule") != new.get("schedule"):
            diff["schedule"] = {"old_keys": list(old.get("schedule", {})), "new_keys": list(new.get("schedule", {}))}
        
        # Allocations diff
        old_alloc = old.get("allocations", {})
        new_alloc = new.get("allocations", {})
        alloc_diff = {}
        for c in set(old_alloc) | set(new_alloc):
            oa = old_alloc.get(c, {})
            na = new_alloc.get(c, {})
            if oa != na:
                alloc_diff[c] = {"old": oa, "new": na}
        if alloc_diff:
            diff["allocations"] = alloc_diff
        return diff

    def execute_auto_apply(
        self,
        workflow_id: str,
        base_version: int,
        proposed_config: Dict[str, Any],
        rationale: str,
        sim_minute: int,
        sim_ts: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        pid = f"auto_{uuid.uuid4().hex[:12]}"
        body = {
            "proposal_id": pid,
            "base_version": base_version,
            "proposed_config": proposed_config,
            "rationale": rationale,
        }
        if evidence:
            body["evidence"] = evidence

        r = self.http.put(f"/workflows/{workflow_id}/config", json=body)
        if r.status_code == 200:
            data = r.json()
            new_v = data["version"]
            self.storage.log_audit(
                sim_minute=sim_minute,
                ts=sim_ts,
                workflow_id=workflow_id,
                actor="controller_auto",
                action="auto_applied",
                version=new_v,
                summary=f"Auto-applied config v{new_v}: {rationale}",
                details={"proposal_id": pid, "changed_dims": data.get("changed_dims")},
            )
            return new_v
        else:
            self.storage.log_audit(
                sim_minute=sim_minute,
                ts=sim_ts,
                workflow_id=workflow_id,
                actor="controller_auto",
                action="auto_apply_failed",
                version=base_version,
                summary=f"Auto-apply rejected ({r.status_code}): {r.text}",
                details={"proposal_id": pid, "response": r.json() if r.status_code < 500 else r.text},
            )
            return None

    def submit_proposal(
        self,
        workflow_id: str,
        base_version: int,
        current_config: Dict[str, Any],
        proposed_config: Dict[str, Any],
        change_summary: str,
        rationale: str,
        affected_leads: int,
        dry_run: Dict[str, Any],
        impact_score: float,
        sim_minute: int,
        sim_ts: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        pid = f"prop_{uuid.uuid4().hex[:12]}"
        diff = self.compute_diff(current_config, proposed_config)
        if not diff:
            return None

        body = {
            "proposal_id": pid,
            "workflow_id": workflow_id,
            "base_version": base_version,
            "proposed_config": proposed_config,
            "change_summary": change_summary,
            "diff": diff,
            "affected_leads": max(int(affected_leads), 0),
            "dry_run": dry_run,
            "impact_score": max(0.0, min(1.0, float(impact_score))),
            "rationale": rationale,
        }
        if evidence:
            body["evidence"] = evidence

        # Record locally first for audit durability
        prop_record = {
            "proposal_id": pid,
            "workflow_id": workflow_id,
            "base_version": base_version,
            "proposed_config": proposed_config,
            "change_summary": change_summary,
            "diff": diff,
            "affected_leads": body["affected_leads"],
            "dry_run": dry_run,
            "impact_score": body["impact_score"],
            "rationale": rationale,
            "evidence": evidence,
            "status": "submitting",
            "created_minute": sim_minute,
        }
        self.storage.save_proposal(prop_record)

        r = self.http.post("/approvals", json=body)
        if r.status_code == 200:
            data = r.json()
            aid = data["approval_id"]
            status = data.get("status", "pending")
            self.storage.update_proposal_status(pid, status, approval_id=aid)
            self.storage.log_audit(
                sim_minute=sim_minute,
                ts=sim_ts,
                workflow_id=workflow_id,
                actor="controller",
                action="approval_requested",
                version=base_version,
                summary=f"Approval requested {aid}: {change_summary}",
                details={"proposal_id": pid, "approval_id": aid, "impact_score": impact_score},
            )
            return aid
        else:
            self.storage.update_proposal_status(pid, "submission_failed", rejection_reasons=[r.text])
            self.storage.log_audit(
                sim_minute=sim_minute,
                ts=sim_ts,
                workflow_id=workflow_id,
                actor="controller",
                action="proposal_rejected_immediate",
                version=base_version,
                summary=f"Approval submission rejected ({r.status_code}): {r.text}",
                details={"proposal_id": pid, "response": r.text},
            )
            return None

    def reconcile_pending_approvals(self, sim_minute: int, sim_ts: str):
        """Checks and processes all pending and approved proposals."""
        pending = self.storage.get_pending_proposals()
        for prop in pending:
            aid = prop.get("approval_id")
            if not aid:
                continue
            r = self.http.get(f"/approvals/{aid}")
            if r.status_code != 200:
                continue
            data = r.json()
            status = data.get("status")
            wid = prop["workflow_id"]

            if status == "approved":
                # Immediately apply approved proposal before apply_by expires
                apply_res = self.http.post(f"/workflows/{wid}/apply", json={"approval_id": aid})
                if apply_res.status_code == 200:
                    res_data = apply_res.json()
                    new_v = res_data["version"]
                    self.storage.update_proposal_status(
                        prop["proposal_id"], "applied", applied_version=new_v, decided_minute=sim_minute
                    )
                    self.storage.log_audit(
                        sim_minute=sim_minute,
                        ts=sim_ts,
                        workflow_id=wid,
                        actor="controller_approved",
                        action="approval_applied",
                        version=new_v,
                        summary=f"Applied approved change {aid} -> v{new_v}",
                        details={"approval_id": aid, "proposal_id": prop["proposal_id"]},
                    )
                elif apply_res.status_code == 409:
                    # Stale base version (e.g. supervisor edit occurred)
                    self.storage.update_proposal_status(
                        prop["proposal_id"], "stale", decided_minute=sim_minute,
                        rejection_reasons=["stale_base_version"]
                    )
                    self.storage.log_audit(
                        sim_minute=sim_minute,
                        ts=sim_ts,
                        workflow_id=wid,
                        actor="controller",
                        action="apply_stale_conflict",
                        version=prop["base_version"],
                        summary=f"Could not apply {aid}: stale base version due to supervisor edit",
                        details={"approval_id": aid},
                    )
                elif apply_res.status_code == 410:
                    self.storage.update_proposal_status(
                        prop["proposal_id"], "lapsed", decided_minute=sim_minute
                    )
            elif status in ("rejected", "expired"):
                self.storage.update_proposal_status(
                    prop["proposal_id"], status, decided_minute=sim_minute,
                    rejection_reasons=data.get("reasons", [])
                )
                self.storage.log_audit(
                    sim_minute=sim_minute,
                    ts=sim_ts,
                    workflow_id=wid,
                    actor="client_approver",
                    action=f"proposal_{status}",
                    version=prop["base_version"],
                    summary=f"Proposal {aid} {status}: {data.get('reasons')}",
                    details={"approval_id": aid, "reasons": data.get("reasons")},
                )
