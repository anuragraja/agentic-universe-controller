"""Canonical Cohort definition and matching engine.

Matches simulator specification:
- Ordered list of up to 20 cohorts.
- First match wins; unmatched leads fall to 'default'.
- Each 'where' clause is AND across features and OR within feature values.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

VALID_FEATURES = {
    "lang": ["hi", "en", "ta", "te", "kn", "mr", "bn"],
    "city_tier": ["1", "2", "3"],
    "age_band": ["18-30", "31-45", "46-60", "60+"],
    "value_band": ["low", "mid", "high"],
}


def matches_where(features: Dict[str, str], where: Dict[str, List[str]]) -> bool:
    """AND across feature keys; OR within feature values."""
    for feat, allowed_vals in where.items():
        val = str(features.get(feat, ""))
        if val not in allowed_vals:
            return False
    return True


def classify_lead(features: Dict[str, str], cohorts: List[Dict[str, Any]]) -> str:
    """Classifies a lead into the first matching cohort or 'default'."""
    for c in cohorts:
        cid = c.get("id")
        where = c.get("where", {})
        if cid and matches_where(features, where):
            return cid
    return "default"


def count_cohort_breakdown(leads: List[Dict[str, str]], cohorts: List[Dict[str, Any]]) -> Dict[str, int]:
    """Computes lead counts across cohorts for a sample of leads."""
    counts = {"default": 0}
    for c in cohorts:
        counts[c["id"]] = 0
    for l in leads:
        cid = classify_lead(l, cohorts)
        counts[cid] = counts.get(cid, 0) + 1
    return counts


def validate_cohorts(cohorts: List[Dict[str, Any]]) -> List[str]:
    """Validates cohorts against simulator constraints."""
    problems = []
    if len(cohorts) > 20:
        problems.append("at most 20 cohorts allowed")
    seen_ids = set()
    for i, c in enumerate(cohorts):
        cid = c.get("id")
        if not isinstance(cid, str) or not cid or cid == "default" or cid in seen_ids:
            problems.append(f"cohorts[{i}].id must be a unique non-empty string other than 'default'")
        else:
            seen_ids.add(cid)
        where = c.get("where") or {}
        for feat, vals in where.items():
            if feat not in VALID_FEATURES:
                problems.append(f"cohort {cid}: unknown feature {feat}")
            elif not isinstance(vals, list) or not vals or any(v not in VALID_FEATURES[feat] for v in vals):
                problems.append(f"cohort {cid}: bad values for {feat}: {vals}")
    return problems


def propose_standard_cohorts(workflow_id: str, languages: List[str]) -> List[Dict[str, Any]]:
    """Proposes high-impact, non-fragmenting cohorts.
    
    Rather than combinatorial explosion (4 ages x 7 langs x 3 tiers = 84),
    we create distinct cohorts along key business dimensions:
    1. Senior citizens (60+) - strong morning preference & high engagement sensitivity
    2. Young adults (18-30) - evening preference
    3. Regional language cohorts if non-English/non-Hindi has >15% share
    """
    cohorts = [
        {
            "id": "seniors",
            "where": {"age_band": ["60+"]}
        },
        {
            "id": "young_adults",
            "where": {"age_band": ["18-30"]}
        }
    ]
    # Add regional language if relevant
    for lang in languages:
        if lang not in ("en", "hi"):
            cohorts.append({
                "id": f"lang_{lang}",
                "where": {"lang": [lang]}
            })
    return cohorts[:10]
