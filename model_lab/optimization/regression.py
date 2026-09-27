"""Frozen core-benchmark regression for routing policies, plus stochastic tolerance.

``evaluate_policy`` replays a routing choice function over every (core case,
tier) pair using per-action evidence (``benchmark_evidence.evidence_table``).
Deterministic grades are compared exactly (zero regression by default);
rubric/human scores, which are stochastic, use a paired bootstrap
non-inferiority test instead of demanding identical numbers.
"""

from __future__ import annotations

import random
from statistics import mean
from typing import Any, Callable, Iterable, Mapping, Sequence

from model_lab.datasets import role_of
from model_lab.optimization.benchmark_evidence import case_context
from model_lab.schemas import Case

Chooser = Callable[[Mapping[str, Any], Sequence[str]], "str | None"]


def eligible_for(context: Mapping[str, Any], tier_actions: Mapping[str, Sequence[str]], registry: Iterable[Mapping[str, Any]]) -> list[str]:
    """Descriptive eligibility (observed tier entitlements + registry capacity/capabilities)."""
    by_action = {f"{m['provider']}/{m['model']}": m for m in registry}
    out = []
    for action in sorted(tier_actions.get(context["tier"], ())):
        model = by_action.get(action)
        if model is None or context["estimated_input_tokens"] > model["max_context_tokens"]:
            continue
        if context["requires_structured_output"] and not model["supports_structured_output"]:
            continue
        if context["requires_tools"] and not model["supports_tools"]:
            continue
        out.append(action)
    return out


def estimated_cost(context: Mapping[str, Any], action: str, registry: Iterable[Mapping[str, Any]], output_tokens: int = 500) -> float | None:
    for m in registry:
        if f"{m['provider']}/{m['model']}" == action:
            return context["estimated_input_tokens"] * m["estimated_input_cost_per_token"] + output_tokens * m["estimated_output_cost_per_token"]
    return None


def evaluate_policy(choose: Chooser, cases: Iterable[Case], evidence: Mapping[tuple[str, str], Mapping[str, Any]], *,
                    tier_actions: Mapping[str, Sequence[str]], registry: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per (case, tier) choice -> outcome, aggregated overall / by domain / tier / role."""
    rows = []
    for case in cases:
        for tier in sorted(tier_actions):
            context = case_context(case, tier)
            eligible = eligible_for(context, tier_actions, registry)
            if not eligible:
                continue
            action = choose(context, eligible)
            outcome = evidence.get((case.case_id, action)) if action else None
            rows.append({"case_id": case.case_id, "domain": case.domain, "tier": tier, "role": role_of(case), "action": action,
                         "supported": outcome is not None, "passed": outcome["passed"] if outcome else None,
                         "rubric": mean(outcome["rubric_scores"]) if outcome and outcome["rubric_scores"] else None,
                         "latency_ms": outcome["latency_ms"] if outcome else None,
                         "estimated_cost": estimated_cost(context, action, registry) if action else None,
                         "evidence_class": outcome["evidence_class"] if outcome else None})
    return {"rows": rows, "overall": _aggregate(rows), "by_domain": _group(rows, "domain"), "by_tier": _group(rows, "tier"),
            "by_role": _group(rows, "role"), "unsupported": sorted({(r["case_id"], r["action"]) for r in rows if not r["supported"]})}


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decided = [r for r in rows if r["passed"] is not None]
    latencies = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    costs = [r["estimated_cost"] for r in rows if r["estimated_cost"] is not None]
    rubric = [r["rubric"] for r in rows if r["rubric"] is not None]
    actions: dict[str, int] = {}
    for r in rows:
        actions[str(r["action"])] = actions.get(str(r["action"]), 0) + 1
    return {"n": len(rows), "decided": len(decided), "abstained": len(rows) - len(decided),
            "deterministic_pass_rate": (sum(r["passed"] for r in decided) / len(decided)) if decided else None,
            "rubric_mean": mean(rubric) if rubric else None, "latency_ms_mean": mean(latencies) if latencies else None,
            "estimated_cost_mean": mean(costs) if costs else None, "action_distribution": dict(sorted(actions.items())),
            "unsupported": sum(not r["supported"] for r in rows)}


def _group(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    return {k: _aggregate(v) for k, v in sorted(groups.items())}


def deterministic_regressions(candidate: Mapping[str, Any], baseline: Mapping[str, Any], *, allowed_drop: float = 0.0,
                              group: str = "by_domain") -> list[str]:
    """Groups where the candidate's deterministic pass rate is below baseline by more than allowed_drop."""
    out = []
    for name, base in baseline[group].items():
        cand = candidate[group].get(name)
        if base["deterministic_pass_rate"] is None:
            continue
        if cand is None or cand["deterministic_pass_rate"] is None:
            out.append(f"{name}: no decided candidate outcomes (baseline {base['deterministic_pass_rate']:.3f})")
        elif cand["deterministic_pass_rate"] < base["deterministic_pass_rate"] - allowed_drop - 1e-12:
            out.append(f"{name}: {cand['deterministic_pass_rate']:.3f} < baseline {base['deterministic_pass_rate']:.3f}")
    return out


def non_inferior(candidate: Sequence[float], baseline: Sequence[float], *, margin: float, seed: int = 0,
                 resamples: int = 1000, confidence: float = 0.95) -> dict[str, Any]:
    """Paired bootstrap on per-item differences: non-inferior iff lower bound of mean(cand-base) >= -margin."""
    if len(candidate) != len(baseline):
        raise ValueError("paired samples required")
    if not candidate:
        return {"n": 0, "non_inferior": None, "reason": "no paired stochastic scores"}
    diffs = [c - b for c, b in zip(candidate, baseline, strict=True)]
    rng = random.Random(seed)
    means = sorted(mean(rng.choice(diffs) for _ in diffs) for _ in range(resamples))
    lower = means[int((1 - confidence) / 2 * resamples)]
    return {"n": len(diffs), "mean_difference": mean(diffs), "lower_bound": lower, "margin": margin,
            "non_inferior": lower >= -margin}
