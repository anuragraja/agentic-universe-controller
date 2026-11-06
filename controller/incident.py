"""Incident detection, LLM prompt remediation, and validation manager."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple


class IncidentManager:
    def __init__(self, flag_threshold: float = 0.03, min_calls: int = 100):
        self.flag_threshold = flag_threshold
        self.min_calls = min_calls

    def check_hallucination_incident(
        self,
        current_prompt: str,
        qa_stats: Dict[str, int],
    ) -> Tuple[bool, float, str]:
        """Evaluates whether current prompt is hallucinating above acceptable threshold.
        
        Args:
            current_prompt: ID of active prompt
            qa_stats: {'connected': int, 'halluc_flags': int}
            
        Returns:
            (is_incident, estimated_halluc_rate, summary)
        """
        connected = qa_stats.get("connected", 0)
        flags = qa_stats.get("halluc_flags", 0)

        if connected < self.min_calls:
            return False, 0.0, f"Insufficient sample ({connected} < {self.min_calls})"

        observed_flag_rate = flags / connected

        # Under simulator model:
        # P(flag) = h * 0.8 + (1 - h) * 0.01 = 0.79 * h + 0.01
        # => h_est = max(0, (P(flag) - 0.01) / 0.79)
        est_halluc = max(0.0, (observed_flag_rate - 0.01) / 0.79)

        if observed_flag_rate >= self.flag_threshold and est_halluc >= 0.02:
            return (
                True,
                est_halluc,
                f"ALERT: Hallucination spike detected on {current_prompt}! Observed flag rate: {observed_flag_rate:.2%}, estimated true hallucination: {est_halluc:.2%} (threshold: {self.flag_threshold:.2%})"
            )

        return False, est_halluc, f"Normal operation: estimated hallucination {est_halluc:.2%}"

    def select_best_fix(
        self,
        workflow_id: str,
        current_prompt: str,
        options: List[str],
        http_client: Any,
        min_validation_pass_rate: float = 0.97,
    ) -> Optional[Tuple[str, str, float]]:
        """Finds and validates a safe prompt version using LLM suggestions and validation endpoint.
        
        Returns:
            (best_prompt_version, validation_run_id, pass_rate) or None
        """
        # 1. Ask LLM for candidate fixes
        candidates = []
        try:
            r = http_client.post("/llm/suggest-fixes", json={
                "workflow_id": workflow_id,
                "problem": f"Severe hallucination incident detected on prompt {current_prompt}. Need safe, grounded alternative."
            })
            if r.status_code == 200:
                suggs = r.json().get("suggestions", [])
                candidates = [s["prompt_version"] for s in suggs if s.get("prompt_version") in options]
        except Exception:
            pass

        # If LLM didn't return valid candidates, fallback to other options
        if not candidates:
            candidates = [p for p in options if p != current_prompt]

        # 2. Run synthetic validation on candidates
        best_candidate = None
        best_run_id = None
        best_pass_rate = 0.0

        for cand in candidates:
            try:
                # n=200 costs ceil(200/100) = 2 credits
                vr = http_client.post("/validation/runs", json={
                    "workflow_id": workflow_id,
                    "prompt_version": cand,
                    "n": 200
                })
                if vr.status_code == 200:
                    data = vr.json()
                    pass_rate = data.get("pass_rate", 0.0)
                    run_id = data.get("validation_run_id")
                    if pass_rate >= min_validation_pass_rate and pass_rate > best_pass_rate:
                        best_candidate = cand
                        best_run_id = run_id
                        best_pass_rate = pass_rate
            except Exception:
                continue

        if best_candidate and best_run_id:
            return best_candidate, best_run_id, best_pass_rate
        return None
