"""Deterministic, deliberately narrow graders for ModelLab observations.

These functions grade observable properties only.  Semantic rubric quality is
represented as an explicit abstention so a formatting check cannot masquerade
as factual or human judgement.
"""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from .schemas import Attempt, AttemptStatus, Case, Grade, utc_now, stable_hash


NON_SUCCESS = {status.value for status in AttemptStatus if status is not AttemptStatus.SUCCESS}


def _grade(grader_id: str, method: str, passed: bool | None, score: float | None,
           reason: str | None, evidence: dict[str, Any], attempt_id: str) -> Grade:
    return Grade(
        grade_id=f"grade-{stable_hash({'attempt': attempt_id, 'grader': grader_id, 'evidence': evidence})[:32]}",
        attempt_id=attempt_id, grader_id=grader_id, grader_version="1.0",
        method=method, passed=passed, score=score, failure_reason=reason,
        evidence={"grader_type": grader_id, "inputs_used": ["candidate_output", "reference_answer"], **evidence},
        created_at=utc_now(),
    )


def _abstain(grader_id: str, attempt_id: str, reason: str, **evidence: Any) -> Grade:
    method = grader_id if grader_id in {"exact_json", "exact_text", "rubric", "schema", "imported"} else "imported"
    return _grade(grader_id, method, None, None, reason, evidence, attempt_id)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def normalize_text(value: str) -> str:
    """Conservative normalization: case/whitespace/punctuation, not paraphrase."""
    value = re.sub(r"\s+", " ", value.strip()).casefold()
    return re.sub(r"\s*([,.;:!?])\s*", r"\1", value)


def grade_exact_text(candidate: str, reference: str, *, attempt_id: str) -> Grade:
    # Ignore transport-added boundary whitespace while keeping the comparison
    # exact for the substantive answer.
    candidate, reference = candidate.strip(), reference.strip()
    passed = candidate == reference
    return _grade("exact_text", "exact_text", passed, 1.0 if passed else 0.0,
                  None if passed else "text does not exactly match reference", {"candidate": candidate, "reference": reference}, attempt_id)


def grade_normalized_text(candidate: str, reference: str, *, attempt_id: str) -> Grade:
    normalized_candidate, normalized_reference = normalize_text(candidate), normalize_text(reference)
    passed = normalized_candidate == normalized_reference
    return _grade("normalized_text", "exact_text", passed, 1.0 if passed else 0.0,
                  None if passed else "normalized text does not match reference",
                  {"candidate_normalized": normalized_candidate, "reference_normalized": normalized_reference}, attempt_id)


def _json_load(value: Any) -> tuple[Any | None, str | None]:
    if not isinstance(value, str):
        return value, None
    try:
        return json.loads(value), None
    except (TypeError, ValueError) as exc:
        return None, str(exc)


def _json_equal(left: Any, right: Any, tolerance: float = 0.0) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(_json_equal(left[key], right[key], tolerance) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_json_equal(a, b, tolerance) for a, b in zip(left, right))
    return left == right


def grade_exact_json(candidate: Any, reference: Any, *, attempt_id: str, numeric_tolerance: float = 0.0) -> Grade:
    parsed, error = _json_load(candidate)
    if error:
        return _abstain("exact_json", attempt_id, "candidate output is not valid JSON", parse_error=error)
    expected, error = _json_load(reference)
    if error:
        return _abstain("exact_json", attempt_id, "reference answer is not valid JSON", reference_parse_error=error)
    passed = _json_equal(parsed, expected, numeric_tolerance)
    return _grade("exact_json", "exact_json", passed, 1.0 if passed else 0.0,
                  None if passed else "JSON value differs from reference", {"candidate": parsed, "reference": expected, "numeric_tolerance": numeric_tolerance}, attempt_id)


def _schema_check(value: Any, schema: Mapping[str, Any], path: str = "$", *, extra_keys: bool = False) -> list[str]:
    errors: list[str] = []
    kind = schema.get("type")
    type_ok = {"object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
               "number": isinstance(value, (int, float)) and not isinstance(value, bool), "integer": isinstance(value, int) and not isinstance(value, bool),
               "boolean": isinstance(value, bool), "null": value is None}
    if kind in type_ok and not type_ok[kind]:
        return [f"{path} must be {kind}"]
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return errors + [f"{path}.properties must be an object"]
        if not extra_keys and schema.get("additionalProperties") is False:
            errors.extend(f"{path}.{key} is not permitted" for key in value if key not in properties)
        for key, subschema in properties.items():
            if key in value and isinstance(subschema, dict):
                errors.extend(_schema_check(value[key], subschema, f"{path}.{key}", extra_keys=extra_keys))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(_schema_check(item, schema["items"], f"{path}[{index}]", extra_keys=extra_keys))
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path} is not an allowed value")
    return errors


def grade_schema(candidate: Any, schema: Mapping[str, Any], *, attempt_id: str, extra_keys: bool = False) -> Grade:
    parsed, error = _json_load(candidate)
    if error:
        return _abstain("schema", attempt_id, "candidate output is not valid JSON", parse_error=error)
    if not isinstance(schema, Mapping):
        return _abstain("schema", attempt_id, "schema definition is unavailable")
    errors = _schema_check(parsed, schema, extra_keys=extra_keys)
    passed = not errors
    return _grade("schema", "schema", passed, 1.0 if passed else 0.0,
                  None if passed else "; ".join(errors), {"schema": dict(schema), "errors": errors}, attempt_id)


def _numbers(value: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", value):
        try:
            values.append(Decimal(match))
        except InvalidOperation:
            pass
    return values


def grade_arithmetic(candidate: str, expected: int | float | str, *, attempt_id: str, tolerance: float = 0.0) -> Grade:
    expected_decimal = Decimal(str(expected))
    numbers = _numbers(candidate)
    if not numbers:
        return _abstain("arithmetic", attempt_id, "no numeric result found")
    observed = numbers[-1]
    passed = abs(float(observed - expected_decimal)) <= tolerance
    return _grade("arithmetic", "schema", passed, 1.0 if passed else 0.0,
                  None if passed else "reported numeric result is incorrect",
                  {"observed": str(observed), "expected": str(expected_decimal), "tolerance": tolerance}, attempt_id)


def grade_required_fields(candidate: Any, required_fields: Iterable[str], *, attempt_id: str) -> Grade:
    parsed, error = _json_load(candidate)
    if error:
        return _abstain("required_fields", attempt_id, "candidate output is not valid JSON", parse_error=error)
    fields = tuple(required_fields)
    if not isinstance(parsed, dict):
        return _grade("required_fields", "schema", False, 0.0, "candidate JSON is not an object", {"required": list(fields)}, attempt_id)
    missing = [field for field in fields if field not in parsed]
    passed = not missing
    return _grade("required_fields", "schema", passed, 1.0 if passed else 0.0,
                  None if passed else "required fields are missing", {"required": list(fields), "missing": missing}, attempt_id)


def grade_attempt(case: Case, attempt: Attempt) -> Grade:
    """Apply only a deterministic case method; rubric cases abstain."""
    model = {"provider": attempt.model_config.provider, "model": attempt.model_config.model, "revision": attempt.model_config.revision}
    if attempt.status is not AttemptStatus.SUCCESS:
        return _abstain("attempt_status", attempt.attempt_id, f"attempt status is {attempt.status.value}", status=attempt.status.value, model=model)
    if attempt.response_text is None:
        return _abstain("missing_output", attempt.attempt_id, "successful attempt has no response text", model=model)
    method = case.evaluation.method
    if method == "exact_json":
        grade = grade_exact_json(attempt.response_text, case.evaluation.reference_answer, attempt_id=attempt.attempt_id)
    elif method == "exact_text":
        grade = grade_exact_text(attempt.response_text, _text(case.evaluation.reference_answer), attempt_id=attempt.attempt_id)
    elif method == "schema":
        grade = grade_schema(attempt.response_text, case.evaluation.reference_answer, attempt_id=attempt.attempt_id)
    elif method == "rubric":
        grade = _abstain("rubric", attempt.attempt_id, "semantic rubric requires blind human review or calibrated judge", model=model)
    else:
        grade = _abstain("unsupported_method", attempt.attempt_id, f"evaluation method {method} is not deterministic", model=model)
    return Grade(**{**grade.__dict__, "evidence": {**grade.evidence, "model": model, "case_id": case.case_id, "evaluation_method": method}})
