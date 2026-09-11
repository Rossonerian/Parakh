"""Offline post-pilot gates.

These helpers consume already persisted observations and produce reviewable
artifacts.  They never call a provider, infer missing billing data, expose
protected answers, tune on holdout data, or mutate application routing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .errors import ValidationError
from .review import export_blind_review
from .schemas import Attempt, AttemptStatus, Case, Grade, stable_hash, utc_now


def _records(values: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [value for value in values]


def _known_sum(values: Iterable[Any]) -> int | None:
    numbers = list(values)
    if not numbers or any(value is None for value in numbers):
        return None
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in numbers):
        raise ValidationError("usage and cost values must be non-negative integers or null")
    return sum(numbers)


def reconcile_provider_usage(
    attempts: Iterable[Attempt], provider_usage: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconcile provider records with local attempts without estimating gaps.

    Provider records are keyed by ``attempt_id``.  A missing provider record,
    missing cost, or mixed currency keeps the corresponding total unknown
    (``None``), rather than treating the gap as zero.
    """
    attempt_list = list(attempts)
    usage = _records(provider_usage)
    attempt_ids = {attempt.attempt_id for attempt in attempt_list}
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    unknown_ids: list[str] = []
    invalid_ids: list[str] = []
    for record in usage:
        attempt_id = record.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            invalid_ids.append(str(attempt_id))
            continue
        if attempt_id in seen:
            duplicate_ids.append(attempt_id)
        seen.add(attempt_id)
        if attempt_id not in attempt_ids:
            unknown_ids.append(attempt_id)

    matched = [record for record in usage if isinstance(record.get("attempt_id"), str) and record.get("attempt_id") in attempt_ids]
    missing_ids = sorted(attempt_ids - {str(record.get("attempt_id")) for record in matched})
    currencies = {record.get("currency") for record in matched if record.get("currency") is not None}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if len(currencies) > 1:
        currency = None
    provider_cost = _known_sum(record.get("cost_minor") for record in matched)
    local_cost = _known_sum(attempt.cost_minor for attempt in attempt_list)
    provider_input_tokens = _known_sum(record.get("input_tokens") for record in matched)
    provider_output_tokens = _known_sum(record.get("output_tokens") for record in matched)
    local_input_tokens = _known_sum(attempt.input_tokens for attempt in attempt_list)
    local_output_tokens = _known_sum(attempt.output_tokens for attempt in attempt_list)
    return {
        "generated_at": utc_now(),
        "attempt_count": len(attempt_list),
        "provider_record_count": len(usage),
        "matched_count": len(matched),
        "missing_attempt_ids": missing_ids,
        "unknown_provider_attempt_ids": sorted(set(unknown_ids)),
        "duplicate_provider_attempt_ids": sorted(set(duplicate_ids)),
        "invalid_provider_records": invalid_ids,
        "currency": currency,
        "currency_consistent": len(currencies) <= 1,
        "provider_cost_minor": provider_cost,
        "local_cost_minor": local_cost,
        "cost_delta_minor": provider_cost - local_cost if provider_cost is not None and local_cost is not None and currency else None,
        "provider_input_tokens": provider_input_tokens,
        "provider_output_tokens": provider_output_tokens,
        "local_input_tokens": local_input_tokens,
        "local_output_tokens": local_output_tokens,
        "limitations": [
            "Missing provider records, missing cost, and mixed currencies remain unknown rather than zero.",
            "This reconciliation does not create or alter billing ledger entries.",
        ],
    }


def critical_failure_report(
    cases: Iterable[Case], attempts: Iterable[Attempt], grades: Iterable[Grade],
) -> dict[str, Any]:
    """Report observable critical failures without copying protected oracles."""
    case_by_id = {case.case_id: case for case in cases}
    attempt_by_id = {attempt.attempt_id: attempt for attempt in attempts}
    grade_list = list(grades)
    grade_by_attempt: dict[str, list[Grade]] = {}
    for grade in grade_list:
        grade_by_attempt.setdefault(grade.attempt_id, []).append(grade)
    rows: list[dict[str, Any]] = []
    for attempt_id, attempt in sorted(attempt_by_id.items()):
        case = case_by_id.get(attempt.case_id)
        if case is None:
            continue
        case_grades = grade_by_attempt.get(attempt_id, [])
        failed_grades = [grade for grade in case_grades if grade.passed is False]
        status_failure = attempt.status is not AttemptStatus.SUCCESS
        critical = status_failure or bool(failed_grades)
        if not critical:
            continue
        reasons = []
        if status_failure:
            reasons.append(f"attempt_status:{attempt.status.value}")
        reasons.extend(grade.failure_reason for grade in failed_grades if grade.failure_reason)
        rows.append({
            "case_id": case.case_id,
            "family_id": case.family_id,
            "domain": case.domain,
            "complexity_level": case.complexity_level,
            "attempt_id": attempt_id,
            "critical_failure": True,
            "reasons": reasons,
            "grader_ids": sorted({grade.grader_id for grade in failed_grades}),
        })
    return {
        "generated_at": utc_now(),
        "attempt_count": len(attempt_by_id),
        "grade_count": len(grade_list),
        "critical_failure_count": len(rows),
        "rows": rows,
        "protected_oracle_included": False,
        "limitations": ["Criticality is limited to observable attempt failures and deterministic grade failures; semantic severity requires human review."],
    }


def export_stratified_calibration_review(
    cases: Iterable[Case], attempts: Iterable[Attempt], *, sample_size: int,
) -> dict[str, Any]:
    """Export a deterministic, identity-blind calibration sample."""
    if not isinstance(sample_size, int) or sample_size <= 0:
        raise ValidationError("sample_size must be a positive integer")
    case_by_id = {case.case_id: case for case in cases if case.split == "calibration"}
    candidates = [attempt for attempt in attempts if attempt.case_id in case_by_id]
    if not candidates:
        return {"status": "blocked", "reason": "no_calibration_attempts_available", "sample_size": sample_size, "rows": [], "strata": {}}
    candidates.sort(key=lambda attempt: (case_by_id[attempt.case_id].domain, case_by_id[attempt.case_id].complexity_level, attempt.case_id, attempt.attempt_id))
    strata: dict[tuple[str, int], list[Attempt]] = {}
    for attempt in candidates:
        case = case_by_id[attempt.case_id]
        strata.setdefault((case.domain, case.complexity_level), []).append(attempt)
    selected: list[Attempt] = []
    # Round-robin strata prevents the first large domain from consuming the sample.
    keys = sorted(strata)
    while len(selected) < sample_size and any(strata[key] for key in keys):
        for key in keys:
            if strata[key] and len(selected) < sample_size:
                selected.append(strata[key].pop(0))
    rows = export_blind_review(selected, include_prompt=False)
    counts: dict[str, int] = {}
    for attempt in selected:
        case = case_by_id[attempt.case_id]
        key = f"{case.domain}:level-{case.complexity_level}"
        counts[key] = counts.get(key, 0) + 1
    return {
        "status": "ready",
        "sample_size": sample_size,
        "selected_count": len(selected),
        "rows": rows,
        "strata": counts,
        "candidate_identity_hidden": True,
        "protected_oracle_included": False,
        "limitations": ["Calibration review material contains candidate outputs only; reviewers must not receive provider, model, cost, latency, or ranking metadata."],
    }


def calibration_selection_report(
    review_records: Iterable[Mapping[str, Any]], *, policy_candidates: Sequence[str], selected_policy_id: str | None = None,
) -> dict[str, Any]:
    """Record calibration selection status without silently selecting a policy."""
    candidates = list(policy_candidates)
    if len(set(candidates)) != len(candidates) or any(not isinstance(value, str) or not value for value in candidates):
        raise ValidationError("policy_candidates must contain unique non-empty identifiers")
    records = _records(review_records)
    if selected_policy_id is not None and selected_policy_id not in candidates:
        raise ValidationError("selected_policy_id is not a policy candidate")
    return {
        "generated_at": utc_now(),
        "policy_candidates": candidates,
        "review_count": len(records),
        "selected_policy_id": selected_policy_id,
        "selection_status": "selected" if selected_policy_id else "owner_review_required",
        "selection_evidence_hash": stable_hash(records) if records else None,
        "limitations": ["No policy is selected automatically; an owner must record the choice after reviewing calibration evidence."],
    }


def consume_holdout_evaluation(
    lock_path: str | Path, *, policy_hash: str, config_hash: str, holdout_case_ids: Sequence[str], tuning: bool = False,
) -> dict[str, Any]:
    """Consume a one-time holdout gate and persist the frozen hashes."""
    if tuning:
        raise ValidationError("holdout cases cannot be used for tuning")
    if not policy_hash or not config_hash or not holdout_case_ids:
        raise ValidationError("holdout evaluation requires policy hash, config hash, and case IDs")
    destination = Path(lock_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    record = {"created_at": utc_now(), "policy_hash": policy_hash, "config_hash": config_hash, "holdout_case_ids": sorted(set(holdout_case_ids)), "purpose": "one_time_evaluation"}
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(record, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
    except FileExistsError as exc:
        raise ValidationError("holdout evaluation has already been consumed") from exc
    return {"status": "consumed", "lock_path": str(destination), **record, "frozen_policy_config_hash": stable_hash({"policy_hash": policy_hash, "config_hash": config_hash})}


def router_replay_shadow(
    recommendations: Iterable[Mapping[str, Any]], *, observed_case_ids: Iterable[str], application_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a replay/shadow artifact without activating or mutating routing."""
    rows = [dict(recommendation) for recommendation in recommendations]
    case_ids = sorted(set(observed_case_ids))
    config_copy = dict(application_config or {})
    config_hash = stable_hash(config_copy)
    return {
        "generated_at": utc_now(),
        "mode": "shadow",
        "recommendation_count": len(rows),
        "observed_case_ids": case_ids,
        "recommendations": rows,
        "application_config_hash_before": config_hash,
        "application_config_hash_after": config_hash,
        "application_config_changed": False,
        "activation_performed": False,
        "limitations": ["Shadow replay is evidence only and cannot alter application configuration or production routing."],
    }
