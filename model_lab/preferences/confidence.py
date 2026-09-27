"""Deterministic classification of user feedback for preference learning.

Classifies user corrections into trainable vs non-trainable categories,
calibrating confidence against objective run evidence and drift indicators.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from model_lab.preferences.schema import Classification
from model_lab.telemetry.schema import RunRecord

HINT_MAP = {
    "factual": "factual_correction",
    "factual_correction": "factual_correction",
    "style": "style_preference",
    "style_preference": "style_preference",
    "schedule": "schedule_detail_change",
    "schedule_detail_change": "schedule_detail_change",
    "repair": "execution_repair",
    "execution_repair": "execution_repair",
    "intent_change": "changed_intent",
    "intent": "changed_intent",
    "true_correction": "true_correction",
    "correction": "true_correction",
}


def classify(feedback: Mapping[str, Any], run: RunRecord) -> Classification:
    """Classify feedback into a category with calibrated confidence and reasons."""
    reasons: list[str] = []

    feedback_type = feedback.get("feedback_type")
    same_request = feedback.get("same_request")
    hint = feedback.get("correction_kind_hint") or feedback.get("kind_hint")
    minutes_after_output = feedback.get("minutes_after_output")
    correction_distance = feedback.get("correction_distance")

    has_tool_failures = any(
        not t.get("execution_success", True) or not t.get("schema_valid", True)
        for t in run.tool_events
    )
    has_val_failures = any(not v.get("passed", True) for v in run.validation_events)
    has_run_failures = has_tool_failures or has_val_failures

    # Category and base confidence
    if same_request is False:
        category = "changed_intent"
        confidence = 0.9
        reasons.append("same_request_false")
    elif feedback_type == "intent_change":
        category = "changed_intent"
        confidence = 0.9
        reasons.append("feedback_type_intent_change")
    elif hint:
        hint_str = str(hint).lower().strip()
        if hint_str in HINT_MAP:
            category = HINT_MAP[hint_str]
            confidence = 0.75
            reasons.append(f"hint_{hint_str}")
        else:
            category = "ambiguous"
            confidence = 0.4
            reasons.append(f"unknown_hint_{hint_str}")
    elif has_run_failures and feedback_type in ("edit", "correction"):
        category = "execution_repair"
        confidence = 0.75
        reasons.append("run_failures_with_edit")
    else:
        category = "ambiguous"
        confidence = 0.35
        reasons.append("no_hint_or_evidence")

    # Modifiers
    if category == "execution_repair" and has_run_failures:
        confidence += 0.1
        reasons.append("supports_execution_repair")

    if (
        minutes_after_output is not None
        and isinstance(minutes_after_output, (int, float))
        and math.isfinite(minutes_after_output)
        and minutes_after_output > 60
    ):
        confidence -= 0.2
        reasons.append("context_drift_gt_60m")

    if (
        correction_distance is not None
        and isinstance(correction_distance, (int, float))
        and math.isfinite(correction_distance)
        and correction_distance >= 0.8
    ):
        confidence -= 0.15
        reasons.append("high_correction_distance")

    if category == "ambiguous":
        confidence = min(confidence, 0.4)

    confidence = max(0.0, min(1.0, round(confidence, 4)))

    return Classification(
        category=category,
        confidence=confidence,
        reasons=tuple(reasons),
    )
