"""off_policy.py: Off-policy evaluation and reward modeling.

Estimates the counterfactual performance of policies using logged data via
IPS, SNIPS, Direct Method, and Doubly Robust estimators, with strict
support and variance warnings.
"""

from typing import Any, Sequence
import random

from model_lab.optimization.router.linucb import fit
from model_lab.optimization.router.features import feature_schema


def _bootstrap_ci(values, weights, seed, bootstrap) -> tuple[float | None, float | None]:
    if not values or bootstrap <= 0:
        return None, None
    rnd = random.Random(seed)
    estimates = []
    for _ in range(bootstrap):
        sum_w = 0.0
        sum_wr = 0.0
        for _ in range(len(values)):
            i = rnd.randrange(len(values))
            w = weights[i]
            sum_w += w
            sum_wr += w * values[i]
        if sum_w > 0:
            estimates.append(sum_wr / sum_w)
    if not estimates:
        return None, None
    estimates.sort()
    return estimates[int((len(estimates) - 1) * 0.025)], estimates[int((len(estimates) - 1) * 0.975)]


def evaluate(
    policy: Any,
    examples: Sequence[dict[str, Any]],
    *,
    reward_key: str = "reward",
    seed: int = 0,
    bootstrap: int = 500,
    min_ess: float = 30.0,
    min_support: float = 0.95,
    propensity_floor: float = 0.01
) -> dict[str, Any]:
    n = len(examples)
    if n == 0:
        return {
            "n": 0, "ips": None, "snips": None, "dm": None, "dr": None, "ess": None, "support": None, "max_weight": None,
            "share_weights_above_10": None, "bootstrap_ci": [None, None], "expected_cost": None, "expected_latency": None,
            "success_rate": None, "critical_failure_rate": None, "action_distribution": {}, "warnings": ["empty"], "reliable": False,
        }

    logged_actions = set(ex["action"] for ex in examples)
    dm_model = fit(
        examples,
        actions=list(logged_actions),
        dimension=feature_schema()["dimension"],
        alpha=0.0,
        lambda_=1.0,
        importance_weighting=False
    )
    
    supported_by_domain = {}
    for ex in examples:
        d = ex.get("task_domain")
        if d not in supported_by_domain:
            supported_by_domain[d] = set()
        if ex["propensity"] >= propensity_floor:
            supported_by_domain[d].add(ex["action"])

    sum_w = 0.0
    sum_w2 = 0.0
    sum_wr = 0.0
    sum_dr = 0.0
    sum_support = 0.0
    max_w = 0.0
    w_above_10_count = 0
    
    action_mass = {}
    
    weights = []
    rewards = []
    
    field_sums = {"cost": 0.0, "latency_ms": 0.0, "success": 0.0, "critical": 0.0}
    field_w_sums = {"cost": 0.0, "latency_ms": 0.0, "success": 0.0, "critical": 0.0}
    field_none = {"cost": False, "latency_ms": False, "success": False, "critical": False}

    sum_dm = 0.0

    for ex in examples:
        pi_i = policy.probabilities(ex)
        a_i = ex["action"]
        r_i = ex[reward_key]
        p_i = ex["propensity"]
        
        w_i = pi_i.get(a_i, 0.0) / p_i
        weights.append(w_i)
        rewards.append(r_i)
        
        sum_w += w_i
        sum_w2 += w_i * w_i
        sum_wr += w_i * r_i
        if w_i > max_w:
            max_w = w_i
        if w_i > 10.0:
            w_above_10_count += 1
            
        for a, p in pi_i.items():
            action_mass[a] = action_mass.get(a, 0.0) + p / n
            
        d = ex.get("task_domain")
        sum_support += sum(pi_i.get(a, 0.0) for a in supported_by_domain.get(d, set()))
        
        dm_val = 0.0
        r_hat_ai = 0.0
        
        overlap_actions = list(pi_i.keys())
        if overlap_actions:
            sc = dm_model.scores(ex["features"], overlap_actions)
            for a, p in pi_i.items():
                dm_val += p * sc.get(a, 0.0)
            
            sc_ai = dm_model.scores(ex["features"], [a_i])
            r_hat_ai = sc_ai.get(a_i, 0.0)
            
        sum_dm += dm_val
        sum_dr += dm_val + w_i * (r_i - r_hat_ai)
        
        if w_i > 0:
            for field in field_sums:
                val = ex.get(field)
                if val is None:
                    field_none[field] = True
                elif not field_none[field]:
                    field_sums[field] += w_i * float(val)
                    field_w_sums[field] += w_i

    ips = sum_wr / n
    snips = sum_wr / sum_w if sum_w > 0 else None  # target puts no mass on any logged action
    dm = sum_dm / n
    dr = sum_dr / n
    ess = (sum_w * sum_w) / sum_w2 if sum_w2 > 0 else 0.0
    support = sum_support / n
    
    ci_lower, ci_upper = _bootstrap_ci(rewards, weights, seed, bootstrap)
    
    warnings = []
    if sum_w == 0:
        warnings.append("no_logged_action_overlap")
    if ci_lower is None:
        warnings.append("bootstrap_no_support")
    if ess < min_ess:
        warnings.append("low_effective_sample_size")
    if support < min_support:
        warnings.append("insufficient_support")
        
    unsupported = [a for a, p in action_mass.items() if p > 0.05 and a not in logged_actions]
    if unsupported:
        unsupported.sort()
        warnings.append(f"unsupported_actions:{','.join(unsupported)}")
        
    if max_w > 20.0:
        warnings.append("extreme_weights")
        
    def _field_res(name):
        if field_none[name] or field_w_sums[name] == 0:
            return None
        return field_sums[name] / field_w_sums[name]

    return {
        "n": n,
        "ips": ips,
        "snips": snips,
        "dm": dm,
        "dr": dr,
        "ess": ess,
        "support": support,
        "max_weight": max_w,
        "share_weights_above_10": w_above_10_count / n,
        "bootstrap_ci": [ci_lower, ci_upper],
        "expected_cost": _field_res("cost"),
        "expected_latency": _field_res("latency_ms"),
        "success_rate": _field_res("success"),
        "critical_failure_rate": _field_res("critical"),
        "action_distribution": action_mass,
        "warnings": warnings,
        "reliable": len(warnings) == 0
    }

def on_policy_value(examples: Sequence[dict[str, Any]], *, seed: int = 0, bootstrap: int = 500) -> dict[str, Any]:
    """Value of the logging policy on its own data: the plain mean reward (exact, no weighting)."""
    n = len(examples)
    if n == 0:
        return {"n": 0, "value": None, "bootstrap_ci": [None, None]}
    rewards = [ex["reward"] for ex in examples]
    ci_lower, ci_upper = _bootstrap_ci(rewards, [1.0] * n, seed, bootstrap)
    return {"n": n, "value": sum(rewards) / n, "bootstrap_ci": [ci_lower, ci_upper]}
