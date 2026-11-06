"""Statistical Testing, Experimentation and Decay Detection.

Implements:
1. Beta-Binomial Bayesian estimation with uninformative or historical priors.
2. Two-sample significance tests with Bonferroni correction for multiple comparisons.
3. Minimum sample size enforcement (prevents false winners on sparse data).
4. Guardrail verification on secondary KPI.
5. Changepoint / EWMA decay detection with automated rollback recommendation.
6. Total-Variation Distance (TVD) computation for governance auto-apply compliance.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def beta_posterior(successes: int, trials: int, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> Tuple[float, float, float]:
    """Computes posterior alpha, beta, and expected mean."""
    a = alpha_prior + successes
    b = beta_prior + max(trials - successes, 0)
    mean = a / (a + b)
    var = (a * b) / (((a + b) ** 2) * (a + b + 1))
    return a, b, mean, var


def two_sample_z_test(k1: int, n1: int, k2: int, n2: int) -> Tuple[float, float]:
    """Computes z-score and one-sided p-value for H1: p2 > p1."""
    if n1 < 10 or n2 < 10:
        return 0.0, 0.5
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se < 1e-9:
        return 0.0, 0.5
    z = (p2 - p1) / se
    # normal cdf approx
    p_val = 0.5 * math.erfc(z / math.sqrt(2))
    return z, p_val


def prob_b_greater_than_a(k_a: int, n_a: int, k_b: int, n_b: int) -> float:
    """Computes P(B > A) using normal approximation to Beta posteriors."""
    _, _, mean_a, var_a = beta_posterior(k_a, n_a)
    _, _, mean_b, var_b = beta_posterior(k_b, n_b)
    diff = mean_b - mean_a
    se = math.sqrt(var_a + var_b)
    if se < 1e-9:
        return 0.5
    z = diff / se
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def calculate_tvd(dist_a: Dict[str, float], dist_b: Dict[str, float]) -> float:
    """Calculates Total Variation Distance (TVD) between two probability distributions:
    TVD = 0.5 * sum(|a_i - b_i|)
    """
    all_keys = set(dist_a.keys()) | set(dist_b.keys())
    diff_sum = sum(abs(dist_a.get(k, 0.0) - dist_b.get(k, 0.0)) for k in all_keys)
    return 0.5 * diff_sum


def max_allocation_shift(old_allocations: Dict[str, Any], new_allocations: Dict[str, Any], dims: List[str]) -> float:
    """Computes the maximum TVD across all cohorts and agent dimensions."""
    cohort_keys = set(old_allocations.keys()) | set(new_allocations.keys())
    worst_shift = 0.0
    for cid in cohort_keys:
        old_cohort = old_allocations.get(cid) or old_allocations.get("default", {})
        new_cohort = new_allocations.get(cid) or new_allocations.get("default", {})
        for dim in dims:
            old_dist = old_cohort.get(dim) or old_allocations.get("default", {}).get(dim, {})
            new_dist = new_cohort.get(dim) or new_allocations.get("default", {}).get(dim, {})
            shift = calculate_tvd(old_dist, new_dist)
            if shift > worst_shift:
                worst_shift = shift
    return worst_shift


class ExperimentAnalyzer:
    def __init__(self, min_sample_size: int = 150, confidence_threshold: float = 0.95):
        self.min_sample_size = min_sample_size
        self.confidence_threshold = confidence_threshold

    def evaluate_dimension(
        self,
        dim: str,
        stats: Dict[str, Dict[str, int]],
        current_alloc: Dict[str, float],
        options: List[str],
        primary_kpi: str = "engagement_rate",
        guardrail_max_drop: float = 0.02,
    ) -> Dict[str, Any]:
        """Analyzes variant metrics on a dimension (e.g. welcome_message or voice).
        
        Returns:
            {
                'winner': Optional[str],
                'is_significant': bool,
                'p_value': float,
                'recommended_alloc': Dict[str, float],
                'summary': str
            }
        """
        # Determine control / baseline variant (highest current weight or first option)
        control = max(current_alloc.items(), key=lambda x: x[1])[0] if current_alloc else options[0]
        control_stats = stats.get(control, {"dials": 0, "connected": 0, "engaged": 0})

        k_metric = "engaged" if primary_kpi == "engagement_rate" else "connected"
        n_metric = "connected" if primary_kpi == "engagement_rate" else "dials"

        ctrl_k = control_stats.get(k_metric, 0)
        ctrl_n = control_stats.get(n_metric, 0)

        num_comparisons = max(len(options) - 1, 1)
        bonferroni_threshold = 1.0 - (1.0 - self.confidence_threshold) / num_comparisons

        best_variant = control
        best_p_win = 0.5
        best_lift = 0.0

        all_tested = True
        for opt in options:
            s = stats.get(opt, {"dials": 0, "connected": 0, "engaged": 0})
            if s.get(n_metric, 0) < self.min_sample_size:
                all_tested = False
            if opt == control:
                continue
            opt_k = s.get(k_metric, 0)
            opt_n = s.get(n_metric, 0)
            if opt_n < self.min_sample_size or ctrl_n < self.min_sample_size:
                continue

            p_win = prob_b_greater_than_a(ctrl_k, ctrl_n, opt_k, opt_n)
            ctrl_rate = ctrl_k / max(ctrl_n, 1)
            opt_rate = opt_k / max(opt_n, 1)
            rel_lift = (opt_rate - ctrl_rate) / max(ctrl_rate, 1e-4)

            # Check secondary guardrail if relevant
            guardrail_passed = True
            if primary_kpi == "engagement_rate":
                # guardrail is pickup rate
                ctrl_pickup = control_stats.get("connected", 0) / max(control_stats.get("dials", 1), 1)
                opt_pickup = s.get("connected", 0) / max(s.get("dials", 1), 1)
                if (ctrl_pickup - opt_pickup) > guardrail_max_drop:
                    guardrail_passed = False
            elif primary_kpi == "pickup_rate":
                # guardrail is engagement rate
                ctrl_eng = control_stats.get("engaged", 0) / max(control_stats.get("connected", 1), 1)
                opt_eng = s.get("engaged", 0) / max(s.get("connected", 1), 1)
                if (ctrl_eng - opt_eng) > guardrail_max_drop:
                    guardrail_passed = False

            if guardrail_passed and p_win > best_p_win and p_win >= bonferroni_threshold:
                best_variant = opt
                best_p_win = p_win
                best_lift = rel_lift

        is_sig = best_variant != control and best_p_win >= bonferroni_threshold

        # Detect clearly inferior variants (e.g. W3 on ks_cancel with 10% penalty)
        inferior = []
        for opt in options:
            if opt == control:
                continue
            s = stats.get(opt, {})
            opt_k = s.get(k_metric, 0)
            opt_n = s.get(n_metric, 0)
            if opt_n >= 80 and ctrl_n >= 80:
                p_win = prob_b_greater_than_a(ctrl_k, ctrl_n, opt_k, opt_n)
                ctrl_rate = ctrl_k / ctrl_n
                opt_rate = opt_k / opt_n
                if p_win <= 0.05 or (opt_rate - ctrl_rate) / max(ctrl_rate, 1e-4) <= -0.05:
                    inferior.append(opt)

        return {
            "control": control,
            "winner": best_variant if is_sig else None,
            "best_variant": best_variant,
            "p_win": best_p_win,
            "lift": best_lift,
            "all_tested": all_tested,
            "is_significant": is_sig,
            "inferior": inferior,
        }

    def detect_decay(
        self,
        variant: str,
        cumulative_stats: Dict[str, int],
        recent_stats: Dict[str, int],
        primary_kpi: str = "engagement_rate",
        drop_threshold: float = 0.08,
    ) -> bool:
        """Detects whether an active variant has decayed relative to historical/peak performance.
        
        Args:
            variant: variant ID
            cumulative_stats: {'connected': ..., 'engaged': ...}
            recent_stats: stats in the last 1-2 days
            drop_threshold: relative drop threshold (e.g. 8%)
        """
        k_metric = "engaged" if primary_kpi == "engagement_rate" else "connected"
        n_metric = "connected" if primary_kpi == "engagement_rate" else "dials"

        cum_n = cumulative_stats.get(n_metric, 0)
        rec_n = recent_stats.get(n_metric, 0)

        if cum_n < 200 or rec_n < 100:
            return False

        cum_rate = cumulative_stats.get(k_metric, 0) / cum_n
        rec_rate = recent_stats.get(k_metric, 0) / rec_n

        rel_drop = (cum_rate - rec_rate) / max(cum_rate, 1e-4)

        if rel_drop >= drop_threshold:
            # Check significance of drop
            z, p_val = two_sample_z_test(
                recent_stats.get(k_metric, 0), rec_n,
                cumulative_stats.get(k_metric, 0), cum_n
            )
            # z > 1.645 indicates cum_rate > rec_rate with p < 0.05
            if z >= 1.645:
                return True
        return False
