"""replay.py: Policy comparison and frontier migration analysis.

Computes offline evaluation reports across policies and segments, and measures
if candidates successfully reduce costs without unacceptable quality regression.
"""

from typing import Any, Sequence
from model_lab.optimization.router.off_policy import evaluate, on_policy_value

def compare(
    policies: list[Any],
    examples: Sequence[dict[str, Any]],
    *,
    segments: tuple[str, ...] = ("task_domain", "tier"),
    **ope_kwargs
) -> dict[str, Any]:
    
    overall = {}
    for p in policies:
        overall[p.name] = evaluate(p, examples, **ope_kwargs)
        
    logging_overall = on_policy_value(examples, seed=ope_kwargs.get("seed", 0))
    
    segments_report = {}
    logging_segments = {}
    
    for seg in segments:
        segments_report[seg] = {}
        logging_segments[seg] = {}
        
        # Group examples by segment value
        groups = {}
        for ex in examples:
            val = ex.get(seg)
            if val is not None:
                if val not in groups:
                    groups[val] = []
                groups[val].append(ex)
                
        for val, group_ex in groups.items():
            segments_report[seg][val] = {}
            for p in policies:
                segments_report[seg][val][p.name] = evaluate(p, group_ex, **ope_kwargs)
            logging_segments[seg][val] = on_policy_value(group_ex, seed=ope_kwargs.get("seed", 0))
            
    return {
        "overall": overall,
        "segments": segments_report,
        "logging": {
            "overall": logging_overall,
            "segments": logging_segments
        }
    }


def frontier_migration(
    candidate: Any,
    baseline: Any,
    examples: Sequence[dict[str, Any]],
    cost_by_action: dict[str, float],
    quality_margin: float = 0.02
) -> dict[str, Any]:
    
    # Group by task_domain
    by_domain = {}
    for ex in examples:
        d = ex.get("task_domain")
        if d not in by_domain:
            by_domain[d] = []
        by_domain[d].append(ex)
        
    per_domain = {}
    non_inferior_cheaper_count = 0
    
    for d, group_ex in by_domain.items():
        cand_rep = evaluate(candidate, group_ex, min_ess=0.0)  # only the value and action distribution are used
        base_rep = evaluate(baseline, group_ex, min_ess=0.0)
        
        cand_val = cand_rep["snips"]
        base_val = base_rep["snips"]
        
        # A sparse logging policy cannot establish quality non-inferiority.
        non_inferior = (
            cand_rep["reliable"] and base_rep["reliable"]
            and cand_val is not None and base_val is not None
            and cand_val >= base_val - quality_margin
        )
        cand_actions = cand_rep["action_distribution"]
        base_actions = base_rep["action_distribution"]
        costs_known = all(a in cost_by_action for a, p in (*cand_actions.items(), *base_actions.items()) if p > 0)
        cand_cost = sum(p * cost_by_action[a] for a, p in cand_actions.items()) if costs_known else None
        base_cost = sum(p * cost_by_action[a] for a, p in base_actions.items()) if costs_known else None
        shifted_to_cheaper = cand_cost < base_cost if costs_known else None

        per_domain[d] = {
            "shifted_to_cheaper": shifted_to_cheaper,
            "candidate_value": cand_val,
            "baseline_value": base_val,
            "non_inferior": non_inferior,
            "cost_known": costs_known,
        }

        if non_inferior and shifted_to_cheaper:
            non_inferior_cheaper_count += 1

    overall_rate = non_inferior_cheaper_count / len(by_domain) if by_domain else None

    return {
        "per_domain": per_domain,
        "overall_rate": overall_rate
    }
