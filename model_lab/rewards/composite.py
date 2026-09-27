"""Composite multi-objective reward calculation and persistence.

Combines deterministic grading, rubric reviews, and user signals into a
reproducible scalar reward with explicit component decomposition, penalty capping,
and auditable missing-data tracking.
"""

from __future__ import annotations

from typing import Any, Iterable

from model_lab.rewards.deterministic import deterministic_from_grade, deterministic_from_run
from model_lab.rewards.normalize import normalize_cost, normalize_latency
from model_lab.rewards.rubric import rubric_for_run, rubric_from_reviews
from model_lab.rewards.schema import (
    RewardComponents,
    RewardConfig,
    RewardRecord,
)
from model_lab.rewards.user_signals import user_signal
from model_lab.schema_registry import REWARD_SCHEMA_VERSION
from model_lab.schemas import Attempt, Grade, HumanReview
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord

STRENGTH_FACTORS = {
    "strong": 1.0,
    "medium": 0.6,
    "weak": 0.3,
}


def _compute_composite_quality(
    deterministic: float | None,
    deterministic_strength: str | None,
    rubric: float | None,
    rubric_strength: str | None,
    user: float | None,
    user_strength: str | None,
    config: RewardConfig,
) -> tuple[float | None, list[str]]:
    """Compute weighted composite quality Q with deterministic dominance.

    Returns:
        (Q, present_strengths)
    """
    qw = config.quality_weights
    available_values: dict[str, float] = {}
    raw_weights: dict[str, float] = {}
    present_strengths: list[str] = []

    if deterministic is not None and deterministic_strength in STRENGTH_FACTORS:
        available_values["deterministic"] = deterministic
        raw_weights["deterministic"] = qw.get("deterministic", 0.6) * STRENGTH_FACTORS[deterministic_strength]
        present_strengths.append(deterministic_strength)

    if rubric is not None and rubric_strength in STRENGTH_FACTORS:
        available_values["rubric"] = rubric
        raw_weights["rubric"] = qw.get("rubric", 0.25) * STRENGTH_FACTORS[rubric_strength]
        present_strengths.append(rubric_strength)

    if user is not None and user_strength in STRENGTH_FACTORS:
        available_values["user"] = user
        raw_weights["user"] = qw.get("user", 0.15) * STRENGTH_FACTORS[user_strength]
        present_strengths.append(user_strength)

    if not available_values:
        return None, present_strengths

    # Enforce deterministic dominance: if D is present, its effective weight >= 0.5
    if "deterministic" in raw_weights:
        w_d = raw_weights["deterministic"]
        sum_other = sum(w for k, w in raw_weights.items() if k != "deterministic")
        if sum_other > 0 and w_d < sum_other:
            raw_weights["deterministic"] = sum_other

    total_w = sum(raw_weights.values())
    if total_w <= 0:
        return None, present_strengths

    Q = sum((w / total_w) * available_values[k] for k, w in raw_weights.items())
    return Q, present_strengths


def reward_for_run(
    run: RunRecord,
    config: RewardConfig,
    *,
    correction_category: str | None = None,
) -> RewardRecord:
    """Compute RewardRecord from a telemetry RunRecord."""
    D, d_comp, s_d = deterministic_from_run(run)
    H, s_h = rubric_for_run(run)
    U, s_u = user_signal(run, correction_category=correction_category)

    Q, present_strengths = _compute_composite_quality(D, s_d, H, s_h, U, s_u, config)

    tool_correct = d_comp.get("tool_correct")
    if len(run.tool_events) > 0:
        tool_failure_penalty = 1.0 - (tool_correct if tool_correct is not None else 0.0)
    else:
        tool_failure_penalty = 0.0

    if (
        run.routing_context.get("requires_structured_output") is True
        and run.outcome.get("structured_output_valid") is False
    ):
        tool_failure_penalty += 1.0

    tool_failure_penalty = min(1.0, max(0.0, tool_failure_penalty))

    retry_count = run.outcome.get("retry_count")
    if retry_count is None or not isinstance(retry_count, int) or retry_count < 0:
        retry_count = 0
    retry_penalty = min(retry_count, 3) / 3.0

    cost_raw = run.outcome.get("final_cost")
    currency = run.outcome.get("currency")
    cost_norm = normalize_cost(cost_raw, currency, run.tier, config)

    latency_raw = run.outcome.get("final_latency_ms")
    latency_norm = normalize_latency(latency_raw, run.routing_context, config)

    missing: list[str] = []
    if cost_norm is None:
        missing.append("cost")
        c_n = 0.0
    else:
        c_n = cost_norm

    if latency_norm is None:
        missing.append("latency")
        l_n = 0.0
    else:
        l_n = latency_norm

    safety_violation = bool(run.outcome.get("critical_failure"))

    # Confidence calculation: max strength factor present * missing multipliers
    if present_strengths:
        base_confidence = max(STRENGTH_FACTORS.get(s, 0.0) for s in present_strengths)
    else:
        base_confidence = 0.0

    confidence = base_confidence
    if "cost" in missing:
        confidence *= 0.8
    if "latency" in missing:
        confidence *= 0.8
    confidence = max(0.0, min(1.0, confidence))

    if safety_violation:
        # A critical failure is never excluded for lack of other signals: it must stay visible to optimizers.
        scalar = config.critical_failure_reward
        excluded_reason = None
    elif Q is None:
        scalar = None
        excluded_reason = "no_quality_signal"
    else:
        wq = config.weights.get("quality", 1.0)
        wc = config.weights.get("cost", 0.2)
        wl = config.weights.get("latency", 0.1)
        wt = config.weights.get("tool_failure", 0.2)
        wr = config.weights.get("retry", 0.1)
        scalar = wq * Q - wc * c_n - wl * l_n - wt * tool_failure_penalty - wr * retry_penalty
        excluded_reason = None

    recovery_success = None
    if retry_count > 0:
        completed = run.outcome.get("completed")
        if isinstance(completed, bool):
            recovery_success = completed

    components = RewardComponents(
        deterministic=D,
        schema_correct=d_comp.get("schema_correct"),
        tool_correct=tool_correct,
        task_completed=d_comp.get("task_completed"),
        rubric=H,
        user_signal=U,
        cost_raw=cost_raw if isinstance(cost_raw, (int, float)) else None,
        currency=str(currency) if currency else None,
        cost_normalized=cost_norm,
        latency_ms=latency_raw if isinstance(latency_raw, (int, float)) else None,
        latency_normalized=latency_norm,
        tool_failure_penalty=tool_failure_penalty,
        retry_penalty=retry_penalty,
        recovery_success=recovery_success,
        safety_violation=safety_violation,
        confidence={
            "overall": confidence,
            "deterministic": STRENGTH_FACTORS.get(s_d, 0.0) if s_d else 0.0,
            "rubric": STRENGTH_FACTORS.get(s_h, 0.0) if s_h else 0.0,
            "user": STRENGTH_FACTORS.get(s_u, 0.0) if s_u else 0.0,
        },
        signal_strength={
            "deterministic": s_d,
            "rubric": s_h,
            "user": s_u,
        },
    )

    metadata: dict[str, Any] = {
        "missing": missing,
        "task_domain": run.task_domain,
        "tier": run.tier,
    }

    config_hash = config.config_hash()
    reward_id = f"rew-{run.run_id}-{REWARD_SCHEMA_VERSION}-{config_hash[:8]}"

    return RewardRecord(
        reward_id=reward_id,
        subject_type="telemetry_run",
        subject_id=run.run_id,
        schema_version=REWARD_SCHEMA_VERSION,
        config_hash=config_hash,
        components=components,
        quality=Q,
        scalar=scalar,
        confidence=confidence,
        excluded_reason=excluded_reason,
        metadata=metadata,
    )


def reward_for_attempt(
    attempt: Attempt,
    grade: Grade,
    reviews: Iterable[HumanReview] | None,
    config: RewardConfig,
) -> RewardRecord:
    """Compute RewardRecord from benchmark Attempt + Grade + HumanReviews."""
    D, d_comp, s_d = deterministic_from_grade(grade)
    H, s_h = rubric_from_reviews(reviews)
    U, s_u = None, None

    Q, present_strengths = _compute_composite_quality(D, s_d, H, s_h, U, s_u, config)

    tool_failure_penalty = 0.0
    retry_penalty = 0.0

    cost_raw = (float(attempt.cost_minor) / 100.0) if attempt.cost_minor is not None else None
    currency = attempt.currency
    cost_norm = normalize_cost(cost_raw, currency, "default", config)

    latency_raw = attempt.completion_latency_ms
    latency_norm = normalize_latency(latency_raw, None, config)

    missing: list[str] = []
    if cost_norm is None:
        missing.append("cost")
        c_n = 0.0
    else:
        c_n = cost_norm

    if latency_norm is None:
        missing.append("latency")
        l_n = 0.0
    else:
        l_n = latency_norm

    safety_violation = (
        grade.failure_reason == "critical_failure"
        or bool(grade.evidence.get("critical_failure"))
    )

    if present_strengths:
        base_confidence = max(STRENGTH_FACTORS.get(s, 0.0) for s in present_strengths)
    else:
        base_confidence = 0.0

    confidence = base_confidence
    if "cost" in missing:
        confidence *= 0.8
    if "latency" in missing:
        confidence *= 0.8
    confidence = max(0.0, min(1.0, confidence))

    if safety_violation:
        # A critical failure is never excluded for lack of other signals: it must stay visible to optimizers.
        scalar = config.critical_failure_reward
        excluded_reason = None
    elif Q is None:
        scalar = None
        excluded_reason = "no_quality_signal"
    else:
        wq = config.weights.get("quality", 1.0)
        wc = config.weights.get("cost", 0.2)
        wl = config.weights.get("latency", 0.1)
        wt = config.weights.get("tool_failure", 0.2)
        wr = config.weights.get("retry", 0.1)
        scalar = wq * Q - wc * c_n - wl * l_n - wt * tool_failure_penalty - wr * retry_penalty
        excluded_reason = None

    components = RewardComponents(
        deterministic=D,
        schema_correct=None,
        tool_correct=None,
        task_completed=D,
        rubric=H,
        user_signal=None,
        cost_raw=cost_raw,
        currency=currency,
        cost_normalized=cost_norm,
        latency_ms=latency_raw,
        latency_normalized=latency_norm,
        tool_failure_penalty=tool_failure_penalty,
        retry_penalty=retry_penalty,
        recovery_success=None,
        safety_violation=safety_violation,
        confidence={
            "overall": confidence,
            "deterministic": STRENGTH_FACTORS.get(s_d, 0.0) if s_d else 0.0,
            "rubric": STRENGTH_FACTORS.get(s_h, 0.0) if s_h else 0.0,
            "user": 0.0,
        },
        signal_strength={
            "deterministic": s_d,
            "rubric": s_h,
            "user": None,
        },
    )

    metadata: dict[str, Any] = {
        "missing": missing,
        "case_id": attempt.case_id,
        "grade_id": grade.grade_id,
    }

    config_hash = config.config_hash()
    reward_id = f"rew-{attempt.attempt_id}-{REWARD_SCHEMA_VERSION}-{config_hash[:8]}"

    return RewardRecord(
        reward_id=reward_id,
        subject_type="benchmark_attempt",
        subject_id=attempt.attempt_id,
        schema_version=REWARD_SCHEMA_VERSION,
        config_hash=config_hash,
        components=components,
        quality=Q,
        scalar=scalar,
        confidence=confidence,
        excluded_reason=excluded_reason,
        metadata=metadata,
    )


def persist(evidence: EvidenceStore, record: RewardRecord) -> bool:
    """Persist reward record to evidence store under kind 'rewards'.

    Record ID format: rew-{subject_id}-{schema_version}-{config_hash[:8]}
    """
    record_id = f"rew-{record.subject_id}-{record.schema_version}-{record.config_hash[:8]}"
    return evidence.append("rewards", record_id, record.to_dict())
