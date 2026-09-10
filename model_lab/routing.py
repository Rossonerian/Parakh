"""Evidence-bound draft routing recommendations; never production router config."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .analysis import ComparisonResult
from .schemas import Case, stable_hash


def draft_recommendations(comparison: ComparisonResult, *, cases: Iterable[Case], eligibility: Mapping[str, bool] | None = None,
                          synthetic: bool = False, minimum_quality: float | None = None) -> list[dict[str, Any]]:
    eligibility = eligibility or {}
    case_list = list(cases)
    candidates = [(comparison.left_label, comparison.left_mean), (comparison.right_label, comparison.right_mean)]
    candidates = [(model, score) for model, score in candidates if eligibility.get(model, True) and score is not None]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    output = []
    for model, score in candidates:
        evidence_id = f"evidence-{stable_hash({'model': model, 'comparison': comparison.to_dict()})[:24]}"
        limitations = list(comparison.limitations)
        if synthetic:
            limitations.append("Synthetic/fake-provider evidence is not real-world model performance.")
        if len(case_list) < 10:
            limitations.append("Small benchmark coverage limits routing confidence.")
        if minimum_quality is not None and score < minimum_quality:
            limitations.append("Observed quality is below the configured minimum; recommendation is ineligible.")
        output.append({"recommendation_id": f"recommendation-{stable_hash({'evidence': evidence_id})[:24]}", "evidence_ids": [evidence_id],
                       "task_condition": {"domains": sorted({case.domain for case in case_list}), "complexity_levels": sorted({case.complexity_level for case in case_list}),
                                           "splits": sorted({case.split for case in case_list})}, "candidate_model": model,
                       "observed_quality": score, "quality_metric": "mean grade score", "eligibility": eligibility.get(model, True) and (minimum_quality is None or score >= minimum_quality),
                       "coverage": {"cases": comparison.matched_cases, "families": len(comparison.family_counts)},
                       "expected_cost": None, "expected_latency_ms": None, "fallback_candidates": [name for name, _ in candidates if name != model],
                       "limitations": limitations, "synthetic": synthetic, "draft_only": True})
    return output

