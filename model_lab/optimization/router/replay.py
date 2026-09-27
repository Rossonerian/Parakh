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
        cand_rep = evaluate(candidate, group_ex, min_ess=0.0) # we only need value and action dist
        base_rep = evaluate(baseline, group_ex, min_ess=0.0)
        
        cand_val = cand_rep["snips"]
        base_val = base_rep["snips"]
        
        non_inferior = (cand_val >= base_val - quality_margin)
        
        # calculate shifted_to_cheaper
        # cand_cost = sum(cand_dist[a] * cost_by_action.get(a, 0)
        # base_cost = sum(base_dist[a] * cost_by_action.get(a, 0)
        # Wait, the prompt says: "shifted_to_cheaper share". This probably means what % of probability mass moved to a strictly cheaper action?
        # Or just "did the expected cost decrease?"
        # "overall rate = share of domains that moved to cheaper actions while non_inferior"
        # "shifted_to_cheaper share" - wait, candidate_cost < baseline_cost?
        
        cand_cost = sum(p * cost_by_action.get(a, 0.0) for a, p in cand_rep["action_distribution"].items())
        base_cost = sum(p * cost_by_action.get(a, 0.0) for a, p in base_rep["action_distribution"].items())
        
        shifted_to_cheaper = (cand_cost < base_cost)
        # We store the bool? or is it a share (float)?
        # "share of domains that moved to cheaper actions while non_inferior" means the overall rate is a share (float).
        # "per task_domain: shifted_to_cheaper share" - wait! If shifted_to_cheaper is a bool per domain, 
        # or maybe we should compute the share (cost reduction) or just a boolean `True/False`?
        # "shifted_to_cheaper share, candidate_value, baseline_value, non_inferior bool"
        # Wait, if `shifted_to_cheaper` is a boolean, then `overall rate = share of domains that ...` makes sense.
        # But wait, what if `shifted_to_cheaper` is the fraction of decisions that became cheaper? No, that requires pairing examples, which we can't do if it's just expected cost over domain.
        # I'll just use a boolean for `shifted_to_cheaper`. Wait, "shifted_to_cheaper share" could mean the boolean. Let's make it a boolean.
        
        per_domain[d] = {
            "shifted_to_cheaper": bool(shifted_to_cheaper),
            "candidate_value": cand_val,
            "baseline_value": base_val,
            "non_inferior": non_inferior
        }
        
        if non_inferior and shifted_to_cheaper:
            non_inferior_cheaper_count += 1
            
    overall_rate = non_inferior_cheaper_count / len(by_domain) if by_domain else 0.0
    
    return {
        "per_domain": per_domain,
        "overall_rate": overall_rate
    }
