"""Trajectory grading across multi-step execution dimensions.

Evaluates state retention, tool precision, error recovery, and execution
correctness across the multi-step reasoning and tool trajectory.
"""

from __future__ import annotations

from typing import Any, Mapping

from model_lab.schema_registry import TRAJECTORY_GRADE_SCHEMA_VERSION
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord


def grade_trajectory(run: RunRecord) -> dict[str, Any]:
    """Grade multi-step trajectory along 4 dimensions:

    - state_retention: context utilization within limits and memory validation checks
    - tool_precision: first-attempt valid schema rate and excess tool call detection
    - error_recovery: bounded error handling without stuck loops or escalation
    - execution_correctness: final completion and validation pass state
    """
    routing_ctx = run.routing_context or {}
    validation_events = run.validation_events or ()
    tool_events = run.tool_events or ()
    outcome = run.outcome or {}

    # 1. State Retention
    requires_memory = routing_ctx.get("requires_memory")
    memory_validators = [
        v for v in validation_events
        if any(k in str(v.get("validator", "")).lower() for k in ("state", "memory"))
    ]

    if requires_memory is False and len(memory_validators) == 0:
        state_retention = {
            "value": None,
            "evidence": ["requires_memory is False and no memory validators present"],
        }
    else:
        ratio = routing_ctx.get("context_utilization_ratio", 0.0)
        token_bloat = ratio > 0.9
        failed_memory = [
            v.get("validator") for v in memory_validators if not v.get("passed", True)
        ]
        ev: list[str] = []
        if token_bloat:
            ev.append(f"token_bloat: utilization {ratio:.3f} > 0.9")
        if failed_memory:
            ev.append(f"memory_validation_failed: {failed_memory}")
        if not token_bloat and not failed_memory:
            ev.append(f"state_retained: utilization={ratio:.3f}")
            val = 1.0
        else:
            val = 0.0
        state_retention = {"value": val, "evidence": ev}

    # 2. Tool Precision
    if len(tool_events) == 0:
        tool_precision = {
            "value": None,
            "evidence": ["no_tool_events"],
        }
    else:
        first_attempts = [e for e in tool_events if e.get("attempt_number", 1) == 1]
        if not first_attempts:
            first_attempts = list(tool_events)
        valid_first = sum(1 for e in first_attempts if e.get("schema_valid") is True)
        rate = float(valid_first) / len(first_attempts)
        planned = routing_ctx.get("tool_count", 0) or 0
        unnecessary = max(0, len(tool_events) - planned)
        tool_precision = {
            "value": rate,
            "evidence": [
                f"first_attempt_schema_valid_rate: {rate:.3f} ({valid_first}/{len(first_attempts)})",
                f"unnecessary_calls: {unnecessary}",
            ],
        }

    # 3. Error Recovery
    malformed_detected = (
        any(not v.get("passed", True) for v in validation_events)
        or any(
            not t.get("schema_valid", True) or not t.get("execution_success", True)
            for t in tool_events
        )
    )
    retry_count = outcome.get("retry_count", 0) or 0
    completed = outcome.get("completed")
    recovered = (completed is True and retry_count > 0)
    bounded = (retry_count <= 3)

    # Loop detection: same tool_name + same error_class/error >= 3 times
    error_counts: dict[tuple[str, str], int] = {}
    for t in tool_events:
        if not t.get("execution_success", True) or not t.get("schema_valid", True) or t.get("error_class") or t.get("error"):
            tool_name = str(t.get("tool_name", "unknown"))
            err = str(t.get("error_class") or t.get("error") or "error")
            key = (tool_name, err)
            error_counts[key] = error_counts.get(key, 0) + 1
    loop_detected = any(c >= 3 for c in error_counts.values())

    escalated = (
        "escalated" in run.status.lower()
        or "escalated" in str(outcome.get("status", "")).lower()
        or (completed is False and bool(outcome.get("error")))
    )

    if not malformed_detected:
        recovery_value = 1.0
    elif recovered and bounded and not loop_detected:
        recovery_value = 1.0
    else:
        recovery_value = 0.0

    error_recovery = {
        "value": recovery_value,
        "evidence": [
            f"malformed_detected={malformed_detected}",
            f"recovered={recovered}",
            f"bounded={bounded}",
            f"loop_detected={loop_detected}",
            f"escalated={escalated}",
        ],
    }

    # 4. Execution Correctness
    if completed is None:
        execution_correctness = {
            "value": None,
            "evidence": ["completed_unknown"],
        }
    else:
        all_passed = all(v.get("passed", True) for v in validation_events)
        val = 1.0 if (completed and all_passed) else 0.0
        execution_correctness = {
            "value": val,
            "evidence": [f"completed={completed}", f"all_validations_passed={all_passed}"],
        }

    return {
        "schema_version": TRAJECTORY_GRADE_SCHEMA_VERSION,
        "trajectory_id": run.run_id,
        "state_retention": state_retention,
        "tool_precision": tool_precision,
        "error_recovery": error_recovery,
        "execution_correctness": execution_correctness,
    }


def persist_trajectory_grade(
    evidence: EvidenceStore,
    trajectory_id: str,
    grade: Mapping[str, Any],
) -> bool:
    """Persist trajectory grade to evidence store under kind 'trajectory_grades'."""
    schema_version = str(grade.get("schema_version", TRAJECTORY_GRADE_SCHEMA_VERSION))
    record_id = f"tg-{trajectory_id}-{schema_version}"
    record = {
        "trajectory_id": trajectory_id,
        "schema_version": schema_version,
        **dict(grade),
    }
    return evidence.append("trajectory_grades", record_id, record)
