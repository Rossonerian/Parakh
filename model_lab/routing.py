"""Evidence-bound draft routing recommendations; never production router config."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .analysis import ComparisonResult
from .schemas import Case, stable_hash


def draft_recommendations(comparison: ComparisonResult, *, cases: Iterable[Case], eligibility: Mapping[str, bool] | None = None,
                          synthetic: bool = False, minimum_quality: float | None = None,
                          critical_failures: Mapping[str, bool | None] | None = None,
                          condition_eligibility: Mapping[str, bool | None] | None = None) -> list[dict[str, Any]]:
    """Return evidence drafts, never an activation-ready model choice.

    Unknown evidence is deliberately represented as an ineligible draft. In
    particular, a missing eligibility entry is not equivalent to approval and
    synthetic fixtures cannot be promoted as real model evidence.
    """
    eligibility = eligibility or {}
    case_list = list(cases)
    candidates = [(comparison.left_label, comparison.left_mean), (comparison.right_label, comparison.right_mean)]
    candidates = [(model, score) for model, score in candidates if score is not None]
    candidates.sort(key=lambda item: (-item[1], item[0]))
    output = []
    for model, score in candidates:
        evidence_id = f"evidence-{stable_hash({'model': model, 'comparison': comparison.to_dict()})[:24]}"
        limitations = list(comparison.limitations)
        known_eligibility = eligibility.get(model)
        eligible = known_eligibility is True
        if known_eligibility is None:
            limitations.append("Eligibility evidence is unavailable; recommendation is ineligible.")
        elif known_eligibility is not True:
            limitations.append("Candidate eligibility evidence is negative; recommendation is ineligible.")
        if synthetic:
            limitations.append("Synthetic/fake-provider evidence is not real-world model performance.")
            eligible = False
        if len(case_list) < 10:
            limitations.append("Small benchmark coverage limits routing confidence.")
            eligible = False
        if comparison.duplicate_case_ids:
            eligible = False
        if comparison.scored_pairs < comparison.matched_cases:
            limitations.append("Paired score coverage is incomplete; unknown grades cannot support promotion.")
            eligible = False
        if critical_failures is None:
            limitations.append("Critical-failure assessment is unavailable; recommendation is ineligible.")
            eligible = False
        elif any(value is not True for value in critical_failures.values()):
            limitations.append("Critical-failure evidence is unknown or blocking; recommendation is ineligible.")
            eligible = False
        if condition_eligibility is None:
            limitations.append("Task-condition eligibility evidence is unavailable; recommendation is ineligible.")
            eligible = False
        elif any(value is not True for value in condition_eligibility.values()):
            limitations.append("Task-condition evidence is unknown or unsupported; recommendation is ineligible.")
            eligible = False
        if minimum_quality is not None and score < minimum_quality:
            limitations.append("Observed quality is below the configured minimum; recommendation is ineligible.")
            eligible = False
        output.append({"recommendation_id": f"recommendation-{stable_hash({'evidence': evidence_id})[:24]}", "evidence_ids": [evidence_id],
                       "task_condition": {"domains": sorted({case.domain for case in case_list}), "complexity_levels": sorted({case.complexity_level for case in case_list}),
                                           "splits": sorted({case.split for case in case_list})}, "candidate_model": model,
                       "observed_quality": score, "quality_metric": "mean grade score", "eligibility": eligible,
                       "coverage": {"cases": comparison.matched_cases, "families": len(comparison.family_counts)},
                       "expected_cost": None, "expected_latency_ms": None, "fallback_candidates": [name for name, _ in candidates if name != model],
                       "limitations": limitations, "synthetic": synthetic, "draft_only": True})
    return output


def check_candidate_eligibility(
    capabilities: Any,
    *,
    required_modalities: tuple[str, ...] = ("text",),
    required_context: int | None = None,
) -> tuple[bool, list[str]]:
    """Check whether a model candidate meets task condition requirements."""
    reasons: list[str] = []
    for mod in required_modalities:
        if hasattr(capabilities, "supports_modality"):
            if not capabilities.supports_modality(mod):
                reasons.append(f"unsupported_modality:{mod}")
        elif hasattr(capabilities, "supported_modalities"):
            if mod.lower() not in {m.lower() for m in capabilities.supported_modalities}:
                reasons.append(f"unsupported_modality:{mod}")
        elif mod != "text":
            reasons.append(f"unsupported_modality:{mod}")
    if required_context and getattr(capabilities, "context_window", None):
        if capabilities.context_window < required_context:
            reasons.append(f"insufficient_context_window:{capabilities.context_window}<{required_context}")
    return (len(reasons) == 0, reasons)
