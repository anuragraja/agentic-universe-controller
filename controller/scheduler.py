"""Call-time optimization: cohort hour weights and per-person preferences.

Optimizes dialling schedules without modifying business dialling windows, cadence or capacity.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def build_hour_weights(
    dialling_window: Tuple[int, int],
    cohorts: List[Dict[str, Any]],
) -> Dict[str, Dict[str, float]]:
    """Builds empirical hour_weights for each cohort within dialling_window [lo, hi).
    
    IMPORTANT: Any hour omitted from a table gets weight 0 in the simulator.
    Therefore, all hours in [lo, hi) MUST be explicitly listed with weight > 0.
    """
    lo, hi = dialling_window
    all_hours = list(range(lo, hi))

    hour_weights: Dict[str, Dict[str, float]] = {}

    # Default table: flat distribution
    hour_weights["default"] = {str(h): 1.0 for h in all_hours}

    # Per-cohort tuning based on demographic pickup archetypes
    for c in cohorts:
        cid = c["id"]
        table = {str(h): 1.0 for h in all_hours}
        where = c.get("where", {})
        age_bands = where.get("age_band", [])

        if "60+" in age_bands or cid in ("seniors", "senior_ta"):
            # Morning archetype: peaks at 9..12
            for h in all_hours:
                if 9 <= h <= 12:
                    table[str(h)] = 2.5
                elif 13 <= h <= 16:
                    table[str(h)] = 1.0
                else:
                    table[str(h)] = 0.5
        elif "18-30" in age_bands or cid in ("young", "young_adults"):
            # Evening archetype: peaks at 17..20
            for h in all_hours:
                if 17 <= h <= 20:
                    table[str(h)] = 3.0
                elif 12 <= h <= 14:
                    table[str(h)] = 1.2
                else:
                    table[str(h)] = 0.5
        elif "31-45" in age_bands or "46-60" in age_bands:
            # Lunch and early evening
            for h in all_hours:
                if 12 <= h <= 14:
                    table[str(h)] = 2.0
                elif 18 <= h <= 20:
                    table[str(h)] = 1.8
                else:
                    table[str(h)] = 1.0

        hour_weights[cid] = table

    return hour_weights


def extract_lead_preferred_hours(
    person_hour_rows: List[Tuple[str, int, int, int]],
    dialling_window: Tuple[int, int],
    max_entries: int = 50_000,
) -> Dict[str, int]:
    """Extracts preferred hour per person based on connected call history.
    
    In the simulator, matching lead_preferred_hour multiplies scheduling score by 6.0,
    and non-matching hours multiply by 0.25.
    """
    lo, hi = dialling_window
    best_hours: Dict[str, Tuple[int, int]] = {}  # person_id -> (best_hour, max_connected)

    for pid, hour, dials, connected in person_hour_rows:
        if not (lo <= hour < hi) or connected <= 0:
            continue
        cur_best = best_hours.get(pid)
        if cur_best is None or connected > cur_best[1]:
            best_hours[pid] = (hour, connected)

    # Return top entries up to max_entries
    out = {}
    for pid, (h, _) in list(best_hours.items())[:max_entries]:
        out[pid] = h
    return out

