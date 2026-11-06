"""Main Autonomous Controller Loop for the Outcome-First Agent."""
from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .cohort import classify_lead, propose_standard_cohorts
from .did_manager import DidManager
from .governance import GovernanceClient
from .incident import IncidentManager
from .ingest import EventIngestor
from .scheduler import build_hour_weights, extract_lead_preferred_hours
from .stats import ExperimentAnalyzer, max_allocation_shift
from .storage import Storage

logger = logging.getLogger("controller")


class Controller:
    def __init__(self, sim_url: str = "http://127.0.0.1:8700", db_path: str = "controller.db", verbose: bool = True):
        self.sim_url = sim_url.rstrip("/")
        self.http = httpx.Client(base_url=self.sim_url, timeout=120)
        self.storage = Storage(db_path)
        self.ingestor = EventIngestor(self.http, self.storage)
        self.governance = GovernanceClient(self.http, self.storage)
        self.did_mgr = DidManager(min_sample=60, degradation_ratio=0.65)
        self.incident_mgr = IncidentManager(flag_threshold=0.03, min_calls=80)
        self.analyzer = ExperimentAnalyzer(min_sample_size=120, confidence_threshold=0.95)
        self.verbose = verbose

        self.workflows: Dict[str, Dict[str, Any]] = {}
        self.current_versions: Dict[str, int] = {}
        self.last_config: Dict[str, Dict[str, Any]] = {}
        self.active_experiments: Dict[str, Dict[str, Any]] = {}

    def log(self, msg: str):
        if self.verbose:
            print(f"[Controller] {msg}", flush=True)

    def bootstrap(self):
        """Discovers workflows, reads current config, and ingests pre-D0 history chunks."""
        self.log(f"Connecting to simulator at {self.sim_url}…")
        r = self.http.get("/workflows")
        if r.status_code != 200:
            raise RuntimeError(f"Simulator unreachable at {self.sim_url}: {r.status_code}")

        for w in r.json():
            wid = w["workflow_id"]
            self.workflows[wid] = w
            cfg_res = self.http.get(f"/workflows/{wid}/config").json()
            self.current_versions[wid] = cfg_res["version"]
            self.last_config[wid] = cfg_res["config"]
            self.log(f"Registered workflow {wid} (v{cfg_res['version']})")

        # Ingest pre-D0 history chunks (C3)
        self.log("Bootstrapping from historical pre-D0 chunks…")
        hist_chunks = self.http.get("/events/chunks", params={"kind": "history"}).json()
        for ch in hist_chunks:
            self.ingestor.ingest_chunk(ch)
        self.log(f"History ingested: {len(hist_chunks)} chunks.")

        # Initialize base cohorts and schedules for workflows
        self._initialize_workflows()

    def _initialize_workflows(self):
        """Sets up baseline cohort definitions and schedule hour weights."""
        sim_st = self.http.get("/sim/state").json()
        sim_minute = sim_st.get("sim_minute", 0)
        sim_ts = sim_st.get("ts", "")

        for wid, w in self.workflows.items():
            cur_cfg = self.last_config[wid]
            cohorts = cur_cfg.get("cohorts") or []
            if not cohorts:
                # Propose sensible, non-fragmenting cohorts based on workflow languages
                new_cohorts = propose_standard_cohorts(wid, w.get("languages", ["hi", "en"]))
                new_cfg = copy.deepcopy(cur_cfg)
                new_cfg["cohorts"] = new_cohorts
                
                # Copy allocations for newly created cohorts from default
                for c in new_cohorts:
                    cid = c["id"]
                    new_cfg["allocations"][cid] = copy.deepcopy(new_cfg["allocations"]["default"])

                # Build hour weights for all cohorts
                win = tuple(w["dialling_window"])
                new_cfg["schedule"]["hour_weights"] = build_hour_weights(win, new_cohorts)

                can_auto, shift, _ = self.governance.can_auto_apply(
                    cur_cfg, new_cfg, ["cohorts", "schedule"], w.get("governance", {})
                )
                if can_auto:
                    v = self.governance.execute_auto_apply(
                        wid, self.current_versions[wid], new_cfg,
                        "Initial cohort and hour weights setup", sim_minute, sim_ts
                    )
                    if v:
                        self.current_versions[wid] = v
                        self.last_config[wid] = new_cfg
                else:
                    # Submit approval if within working hours
                    can_submit, _ = self.governance.can_submit_approval(wid, sim_minute, w.get("governance", {}))
                    if can_submit:
                        self.governance.submit_proposal(
                            workflow_id=wid,
                            base_version=self.current_versions[wid],
                            current_config=cur_cfg,
                            proposed_config=new_cfg,
                            change_summary="Initialize demographic cohorts and peak hour weights",
                            rationale="Targeting age and language cohorts with tailored hours",
                            affected_leads=w.get("daily_batch", {}).get("size", 1000) * 3,
                            dry_run={"expected_pickup_lift": 0.03},
                            impact_score=0.35,
                            sim_minute=sim_minute,
                            sim_ts=sim_ts,
                        )

    def run(self, tick_minutes: int = 60):
        """Runs the simulation loop until finished."""
        self.bootstrap()
        self.log("Starting autonomous control loop…")

        start_wall_time = time.time()
        last_day_log = -1

        while True:
            # 1. Advance simulation clock
            adv_res = self.http.post("/sim/advance", json={"minutes": tick_minutes})
            if adv_res.status_code != 200:
                self.log(f"Advance error: {adv_res.status_code} {adv_res.text}")
                break
            st = adv_res.json()
            sim_minute = st["sim_minute"]
            sim_ts = st["ts"]
            finished = st["finished"]
            current_day = sim_minute // 1440

            if current_day != last_day_log:
                elapsed = time.time() - start_wall_time
                self.log(f"--- Sim Day D{current_day} ({sim_ts}) | Elapsed: {elapsed:.1f}s | Credits: {self.http.get('/sim/state').json().get('credits_remaining')} ---")
                last_day_log = current_day

            # 2. Ingest new chunks
            for ch in st.get("new_chunks", []):
                ingest_res = self.ingestor.ingest_chunk(ch)
                # Handle supervisor edits detected in chunks
                for s_edit in ingest_res.get("supervisor_edits", []):
                    wid = s_edit["workflow_id"]
                    new_v = s_edit["version"]
                    self.current_versions[wid] = new_v
                    # Fetch fresh config
                    fresh_cfg = self.http.get(f"/workflows/{wid}/config").json()["config"]
                    self.last_config[wid] = fresh_cfg
                    self.storage.log_audit(
                        sim_minute=sim_minute,
                        ts=sim_ts,
                        workflow_id=wid,
                        actor="supervisor",
                        action="supervisor_edit_detected",
                        version=new_v,
                        summary=f"Detected external supervisor edit to v{new_v}",
                        details=s_edit,
                    )
                    self.log(f"[{wid}] Supervisor edit detected -> v{new_v}")

            # 3. Reconcile pending approvals (apply approved ones immediately)
            self.governance.reconcile_pending_approvals(sim_minute, sim_ts)

            # Update cached configs for applied changes
            for wid in self.workflows:
                cur_v = self.http.get(f"/workflows/{wid}/config").json()
                if cur_v["version"] != self.current_versions[wid]:
                    self.current_versions[wid] = cur_v["version"]
                    self.last_config[wid] = cur_v["config"]

            # 4. Workflow-level optimizations and incident response
            for wid, w in self.workflows.items():
                self._process_workflow(wid, w, sim_minute, sim_ts, current_day)

            if finished:
                self.log("Simulation finished!")
                break

        final_st = self.http.get("/sim/state").json()
        self.log(f"Final state: {final_st}")

    def _process_workflow(
        self,
        wid: str,
        w: Dict[str, Any],
        sim_minute: int,
        sim_ts: str,
        current_day: int,
    ):
        cur_cfg = self.last_config[wid]
        cur_v = self.current_versions[wid]
        gov_pol = w.get("governance", {})

        # ----------------------------------------------------
        # A. Incident Detection & Mitigation (C8)
        # ----------------------------------------------------
        cur_prompt = cur_cfg.get("prompt_version")
        qa_stats = self.storage.get_prompt_qa_stats(wid, cur_prompt)
        is_incident, est_halluc, inc_summary = self.incident_mgr.check_hallucination_incident(cur_prompt, qa_stats)
        if is_incident:
            self.log(f"[{wid}] {inc_summary}")
            fix_res = self.incident_mgr.select_best_fix(
                wid, cur_prompt, w["options"]["prompt_version"], self.http,
                gov_pol.get("min_validation_pass_rate", 0.97)
            )
            if fix_res:
                safe_prompt, val_run_id, pass_rate = fix_res
                self.log(f"[{wid}] Found validated fix: {safe_prompt} (pass rate: {pass_rate:.1%}, run: {val_run_id})")
                new_cfg = copy.deepcopy(cur_cfg)
                new_cfg["prompt_version"] = safe_prompt
                # Submit emergency proposal
                self.governance.submit_proposal(
                    workflow_id=wid,
                    base_version=cur_v,
                    current_config=cur_cfg,
                    proposed_config=new_cfg,
                    change_summary=f"Emergency: Rollback hallucinating prompt to validated {safe_prompt}",
                    rationale=f"Hallucination spike detected ({est_halluc:.1%}). New prompt validated with {pass_rate:.1%} pass rate.",
                    affected_leads=w.get("daily_batch", {}).get("size", 1000) * 5,
                    dry_run={"hallucination_drop": round(est_halluc, 3), "expected_pass_rate": pass_rate},
                    impact_score=0.95,
                    sim_minute=sim_minute,
                    sim_ts=sim_ts,
                    evidence={"validation_run_id": val_run_id},
                )
                return  # Priority handled

        # ----------------------------------------------------
        # B. Caller-ID Health & Load Balancing (C5)
        # ----------------------------------------------------
        did_opts = w["options"]["caller_id"]
        did_stats = self.storage.get_recent_did_stats(wid, max(0, current_day - 2))
        cur_did_alloc = cur_cfg["allocations"]["default"].get("caller_id", {})
        new_did_alloc, degraded_dids, did_rationale = self.did_mgr.recommend_caller_id_allocation(
            did_opts, did_stats, cur_did_alloc
        )

        if degraded_dids or (new_did_alloc and new_did_alloc != cur_did_alloc and not degraded_dids):
            # Check if change is warranted
            if new_did_alloc != cur_did_alloc:
                new_cfg = copy.deepcopy(cur_cfg)
                for coh_key in new_cfg["allocations"]:
                    new_cfg["allocations"][coh_key]["caller_id"] = copy.deepcopy(new_did_alloc)

                can_auto, shift, _ = self.governance.can_auto_apply(
                    cur_cfg, new_cfg, ["caller_id"], gov_pol
                )
                if can_auto:
                    v = self.governance.execute_auto_apply(
                        wid, cur_v, new_cfg, did_rationale, sim_minute, sim_ts
                    )
                    if v:
                        self.current_versions[wid] = v
                        self.last_config[wid] = new_cfg
                        self.log(f"[{wid}] Auto-applied caller_id rebalance: {new_did_alloc}")
                else:
                    can_sub, _ = self.governance.can_submit_approval(wid, sim_minute, gov_pol)
                    if can_sub:
                        self.governance.submit_proposal(
                            workflow_id=wid,
                            base_version=cur_v,
                            current_config=cur_cfg,
                            proposed_config=new_cfg,
                            change_summary="Rotate degraded caller-IDs and balance load",
                            rationale=did_rationale,
                            affected_leads=w.get("daily_batch", {}).get("size", 1000) * 2,
                            dry_run={"pickup_recovery": 0.05},
                            impact_score=0.6,
                            sim_minute=sim_minute,
                            sim_ts=sim_ts,
                        )

        # ----------------------------------------------------
        # C. Call-Time Preference Updates (C4)
        # ----------------------------------------------------
        # Once every 2 days, update per-person preferred hours
        if sim_minute % (1440 * 2) == 0 and sim_minute > 0:
            pref_hours = extract_lead_preferred_hours(
                self.storage.conn.execute("SELECT person_id, hour, dials, connected FROM person_hours").fetchall(),
                tuple(w["dialling_window"]),
                max_entries=30_000,
            )
            if pref_hours and pref_hours != cur_cfg["schedule"].get("lead_preferred_hour"):
                new_cfg = copy.deepcopy(cur_cfg)
                new_cfg["schedule"]["lead_preferred_hour"] = pref_hours
                can_auto, _, _ = self.governance.can_auto_apply(cur_cfg, new_cfg, ["schedule"], gov_pol)
                if can_auto:
                    v = self.governance.execute_auto_apply(
                        wid, cur_v, new_cfg, "Updated learned per-person preferred call hours", sim_minute, sim_ts
                    )
                    if v:
                        self.current_versions[wid] = v
                        self.last_config[wid] = new_cfg

        # ----------------------------------------------------
        # D. Variant Experimentation & Decay Rollback (C6, C7)
        # ----------------------------------------------------
        # Check active variants once a day at 11:00 (during peak supervisor hours)
        mod_min = sim_minute % 1440
        if 11 * 60 <= mod_min < 12 * 60:
            self._evaluate_experiments(wid, w, sim_minute, sim_ts, current_day)

    def _evaluate_experiments(
        self,
        wid: str,
        w: Dict[str, Any],
        sim_minute: int,
        sim_ts: str,
        current_day: int,
    ):
        cur_cfg = self.last_config[wid]
        cur_v = self.current_versions[wid]
        gov_pol = w.get("governance", {})
        primary_kpi = w.get("objective", {}).get("primary", "engagement_rate")
        guardrail_drop = float(w.get("objective", {}).get("guardrail", {}).get("pickup_rate_max_drop", 0.02))

        candidate_cfg = copy.deepcopy(cur_cfg)
        has_change = False
        change_reasons = []

        cohorts = cur_cfg.get("cohorts", [])
        cohort_ids = ["default"] + [c["id"] for c in cohorts]

        for cid in cohort_ids:
            cur_alloc = cur_cfg["allocations"].get(cid) or cur_cfg["allocations"]["default"]

            for dim in ("voice", "welcome_message"):
                opts = w["options"][dim]
                dim_stats = self.storage.get_cohort_dim_stats(wid, cid, dim)
                cur_dim_alloc = cur_alloc.get(dim, {})

                # 1. Decay detection (C7)
                active_top = max(cur_dim_alloc.items(), key=lambda x: x[1])[0] if cur_dim_alloc else opts[0]
                cum_s = dim_stats.get(active_top, {})
                recent_s = self.storage.get_recent_dim_stats(wid, cid, dim, max(0, current_day - 2)).get(active_top, {})
                if self.analyzer.detect_decay(active_top, cum_s, recent_s, primary_kpi):
                    self.log(f"[{wid}:{cid}] DECAY DETECTED on {dim}={active_top}! Initiating rollback.")
                    # Rollback to baseline (first option) or explore others
                    fallback = [o for o in opts if o != active_top][0]
                    candidate_cfg["allocations"].setdefault(cid, copy.deepcopy(cur_alloc))[dim] = {fallback: 1.0}
                    has_change = True
                    change_reasons.append(f"Rollback decayed {dim}={active_top} to {fallback}")
                    continue

                # 2. Experiment evaluation (C6)
                eval_res = self.analyzer.evaluate_dimension(
                    dim=dim,
                    stats=dim_stats,
                    current_alloc=cur_dim_alloc,
                    options=opts,
                    primary_kpi=primary_kpi,
                    guardrail_max_drop=guardrail_drop,
                )

                if eval_res["is_significant"] and eval_res["winner"]:
                    winner = eval_res["winner"]
                    if cur_dim_alloc.get(winner, 0.0) < 0.8:
                        self.log(f"[{wid}:{cid}] WINNER FOUND: {dim}={winner} (P(win)={eval_res['p_win']:.2f}, lift={eval_res['lift']:+.1%})")
                        # Shift towards winner
                        target_alloc = {winner: 0.8}
                        # keep 20% exploration across others
                        other_opts = [o for o in opts if o != winner]
                        for o in other_opts:
                            target_alloc[o] = round(0.2 / len(other_opts), 3)
                        # normalize
                        tot = sum(target_alloc.values())
                        target_alloc[winner] += round(1.0 - tot, 3)

                        candidate_cfg["allocations"].setdefault(cid, copy.deepcopy(cur_alloc))[dim] = target_alloc
                        has_change = True
                        change_reasons.append(f"Promote winning {dim}={winner} (+{eval_res['lift']:.1%} lift)")

                elif not eval_res["all_tested"] and len(cur_dim_alloc) == 1:
                    # Start initial exploration (split test)
                    split_alloc = {o: round(1.0 / len(opts), 3) for o in opts}
                    tot = sum(split_alloc.values())
                    split_alloc[opts[0]] += round(1.0 - tot, 3)
                    candidate_cfg["allocations"].setdefault(cid, copy.deepcopy(cur_alloc))[dim] = split_alloc
                    has_change = True
                    change_reasons.append(f"Initiate uniform exploration across {dim} variants {opts}")

        if has_change:
            changed_dims = []
            for d in ("voice", "welcome_message"):
                if any(cur_cfg["allocations"].get(c, {}).get(d) != candidate_cfg["allocations"].get(c, {}).get(d) for c in cohort_ids):
                    changed_dims.append(d)

            can_auto, shift, _ = self.governance.can_auto_apply(cur_cfg, candidate_cfg, changed_dims, gov_pol)
            if can_auto:
                v = self.governance.execute_auto_apply(
                    wid, cur_v, candidate_cfg, "; ".join(change_reasons), sim_minute, sim_ts
                )
                if v:
                    self.current_versions[wid] = v
                    self.last_config[wid] = candidate_cfg
                    self.log(f"[{wid}] Auto-applied variant changes: {', '.join(change_reasons)}")
            else:
                can_sub, _ = self.governance.can_submit_approval(wid, sim_minute, gov_pol)
                if can_sub:
                    self.governance.submit_proposal(
                        workflow_id=wid,
                        base_version=cur_v,
                        current_config=cur_cfg,
                        proposed_config=candidate_cfg,
                        change_summary=f"Experiment update: {'; '.join(change_reasons)[:80]}",
                        rationale="; ".join(change_reasons),
                        affected_leads=w.get("daily_batch", {}).get("size", 1000) * 3,
                        dry_run={"lift": 0.04},
                        impact_score=0.45,
                        sim_minute=sim_minute,
                        sim_ts=sim_ts,
                    )
