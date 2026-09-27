"""Deterministic quality component evaluation for telemetry and benchmark runs.

Extracts objective, verifiable quality signals from structured output validations,
tool execution results, and ground-truth grading outcomes.
"""

from __future__ import annotations

from model_lab.schemas import Grade
from model_lab.telemetry.schema import RunRecord


def deterministic_from_run(run: RunRecord) -> tuple[float | None, dict[str, float | None], str | None]:
    """Compute deterministic quality score D and subcomponents from a telemetry run.

    Returns:
        (D, subcomponents_dict, signal_strength)
    """
    requires_structured = run.routing_context.get("requires_structured_output")
    if requires_structured is False:
        schema_correct = None
    else:
        structured_val = run.outcome.get("structured_output_valid")
        if isinstance(structured_val, bool):
            schema_correct = 1.0 if structured_val else 0.0
        else:
            schema_correct = None

    if len(run.tool_events) == 0:
        tool_correct = None
    else:
        valid_count = sum(
            1
            for e in run.tool_events
            if e.get("schema_valid") is True and e.get("execution_success") is True
        )
        tool_correct = float(valid_count) / len(run.tool_events)

    completed_val = run.outcome.get("completed")
    if isinstance(completed_val, bool):
        task_completed = 1.0 if completed_val else 0.0
    else:
        task_completed = None

    available = [x for x in (schema_correct, tool_correct, task_completed) if x is not None]
    if available:
        D = sum(available) / len(available)
        strength = "strong"
    else:
        D = None
        strength = None

    subcomponents = {
        "schema_correct": schema_correct,
        "tool_correct": tool_correct,
        "task_completed": task_completed,
        "deterministic": D,
    }
    return D, subcomponents, strength


def deterministic_from_grade(grade: Grade) -> tuple[float | None, dict[str, float | None], str | None]:
    """Compute deterministic quality score D from benchmark grade.

    Returns:
        (D, subcomponents_dict, signal_strength)
    """
    if grade.passed is True:
        D = 1.0
        strength = "strong"
    elif grade.passed is False:
        D = 0.0
        strength = "strong"
    else:
        D = None
        strength = None

    subcomponents = {
        "schema_correct": None,
        "tool_correct": None,
        "task_completed": D,
        "deterministic": D,
    }
    return D, subcomponents, strength
