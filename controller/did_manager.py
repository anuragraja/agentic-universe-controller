"""Caller-ID health monitoring, load balancing, and incident mitigation."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class DidManager:
    def __init__(self, min_sample: int = 80, degradation_ratio: float = 0.65):
        self.min_sample = min_sample
        self.degradation_ratio = degradation_ratio

    def recommend_caller_id_allocation(
        self,
        options: List[str],
        stats: Dict[str, Dict[str, int]],
        current_alloc: Dict[str, float],
    ) -> Tuple[Dict[str, float], List[str], str]:
        """Evaluates caller-ID health and produces an optimal, load-balanced allocation.
        
        Returns:
            (new_allocation, degraded_dids, rationale)
        """
        if not options:
            return {}, [], "no options"

        # Calculate pickup rates
        rates = {}
        total_dials = 0
        for did in options:
            s = stats.get(did, {"dials": 0, "connected": 0})
            d = s["dials"]
            c = s["connected"]
            total_dials += d
            if d >= self.min_sample:
                rates[did] = c / d

        degraded = []
        if len(rates) >= 2:
            avg_rate = sum(rates.values()) / len(rates)
            for did, rate in rates.items():
                other_rates = [r for d, r in rates.items() if d != did]
                other_avg = sum(other_rates) / len(other_rates) if other_rates else avg_rate
                # Degraded if significantly lower than others
                if rate < other_avg * self.degradation_ratio and (other_avg - rate) >= 0.08:
                    degraded.append(did)

        # Active healthy DIDs
        healthy = [d for d in options if d not in degraded]
        if not healthy:
            healthy = options  # fallback

        # Uniform load balancing across healthy DIDs to minimize (load / l0)^2 saturation
        weight = round(1.0 / len(healthy), 4)
        new_alloc = {d: weight for d in healthy}
        # adjust sum to 1.0
        tot = sum(new_alloc.values())
        if tot > 0:
            first_did = next(iter(new_alloc))
            new_alloc[first_did] += round(1.0 - tot, 4)

        if degraded:
            rationale = (f"Detected degraded caller-IDs {degraded} (pickup < {self.degradation_ratio:.0%} of pool). "
                         f"Load-balanced remaining healthy DIDs: {healthy}")
        else:
            rationale = f"Load-balancing dials uniformly across all {len(healthy)} healthy DIDs to prevent saturation."

        return new_alloc, degraded, rationale
