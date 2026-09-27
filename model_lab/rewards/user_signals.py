"""User proxy signal interpretation for telemetry runs.

Interprets implicit and explicit user signals (accepts, retries, abandons, corrections)
with strict precedence and confidence calibration. Weak proxies never masquerade as strong evidence,
and non-corrective user edits (intent shifts, style changes) remain strictly neutral.
"""

from __future__ import annotations

from model_lab.telemetry.schema import RunRecord

NEGATIVE_CORRECTION_CATEGORIES = {
    "true_correction",
    "factual_correction",
    "execution_repair",
}

NEUTRAL_CORRECTION_CATEGORIES = {
    "changed_intent",
    "style_preference",
    "schedule_detail_change",
    "ambiguous",
}


def user_signal(
    run: RunRecord,
    correction_category: str | None = None,
) -> tuple[float | None, str | None]:
    """Extract calibrated user signal U and signal strength from run feedback and outcomes.

    Precedence:
        1. Negative correction (if labelled) -> 0.0 ("medium")
        2. Neutral correction (changed_intent, style_preference, schedule_detail_change, ambiguous, None) -> None (None)
        3. Abandon -> 0.0 ("weak")
        4. Retry -> 0.2 ("weak")
        5. Accept -> 1.0 ("medium")
        6. Inactive / no signal -> None (None)

    Neutral corrections contribute nothing (neutral, not negative).
    Inactivity is never positive.
    """
    outcome = run.outcome or {}
    feedback = run.feedback or ()

    is_correction = bool(outcome.get("user_correction_signal")) or any(
        f.get("feedback_type") in ("edit", "correction") for f in feedback
    )

    if is_correction:
        if correction_category in NEGATIVE_CORRECTION_CATEGORIES:
            return 0.0, "medium"
        # Neutral correction contributes nothing
        return None, None

    is_abandon = bool(outcome.get("user_abandon_signal")) or any(
        f.get("feedback_type") == "abandon" for f in feedback
    )
    if is_abandon:
        return 0.0, "weak"

    is_retry = bool(outcome.get("user_retry_signal")) or any(
        f.get("feedback_type") == "retry" for f in feedback
    )
    if is_retry:
        return 0.2, "weak"

    is_accept = bool(outcome.get("user_accept_signal")) or any(
        f.get("feedback_type") == "accept" for f in feedback
    )
    if is_accept:
        return 1.0, "medium"

    return None, None
