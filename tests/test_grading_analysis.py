import json

import pytest

from model_lab.analysis import compare_grades, regression_report
from model_lab.grading import (
    grade_arithmetic,
    grade_attempt,
    grade_exact_json,
    grade_exact_text,
    grade_normalized_text,
    grade_required_fields,
    grade_schema,
)
from model_lab.schemas import Attempt, AttemptStatus, Case, ModelConfig, utc_now
from model_lab.benchmark import load_suite


ROOT = __import__("pathlib").Path(__file__).parents[1]


def _attempt(case_id: str, text: str | None, *, model: str = "model-a", status=AttemptStatus.SUCCESS):
    return Attempt(
        attempt_id=f"attempt-{model}-{case_id}",
        run_id="run-1",
        logical_request_id=f"logical-{case_id}",
        case_id=case_id,
        model_config=ModelConfig(provider="fake", model=model),
        prompt_hash="a" * 16,
        response_text=text,
        status=status,
        started_at=utc_now(),
    )


def test_exact_and_normalized_grades_record_provenance_and_fail_wrong_answer():
    exact = grade_exact_text("  Hello\n", "Hello", attempt_id="a1")
    normalized = grade_normalized_text("The  total is INR 250.", "the total is inr 250", attempt_id="a2")
    wrong = grade_exact_text("wrong", "right", attempt_id="a3")

    assert exact.passed is True and exact.score == 1
    assert normalized.passed is True
    assert wrong.passed is False and wrong.score == 0
    assert exact.evidence["inputs_used"] == ["candidate_output", "reference_answer"]
    assert exact.grader_id == "exact_text"


def test_json_schema_arithmetic_and_required_field_graders_are_safe():
    json_grade = grade_exact_json('{"total": 10, "items": [1, 2]}', {"items": [1, 2], "total": 10}, attempt_id="j")
    schema_grade = grade_schema('{"total": 10}', {"type": "object", "required": ["total"], "properties": {"total": {"type": "number"}}}, attempt_id="s")
    arithmetic_grade = grade_arithmetic("Total = 12 + 8 = 20", 20, attempt_id="m")
    fields_grade = grade_required_fields('{"name":"Ada","email":"a@example.test"}', ["name", "email"], attempt_id="f")

    assert json_grade.passed and schema_grade.passed and arithmetic_grade.passed and fields_grade.passed
    assert not grade_arithmetic("Total = 12 + 8 = 21", 20, attempt_id="bad").passed
    assert grade_exact_json("not json", {}, attempt_id="bad-json").passed is None
    assert grade_required_fields("{}", ["name"], attempt_id="missing").passed is False


def test_grade_attempt_abstains_for_non_success_and_rubric_without_semantic_judge():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    case = next(c for c in suite.cases if c.evaluation.method == "exact_json")
    attempt = _attempt(case.case_id, json.dumps(case.evaluation.reference_answer), status=AttemptStatus.TIMEOUT)
    timeout_grade = grade_attempt(case, attempt)
    assert timeout_grade.passed is None and timeout_grade.score is None
    assert "timeout" in (timeout_grade.failure_reason or "")

    rubric_case = next(c for c in suite.cases if c.evaluation.method == "rubric")
    rubric_grade = grade_attempt(rubric_case, _attempt(rubric_case.case_id, "plausible"))
    assert rubric_grade.passed is None and rubric_grade.method == "rubric"
    assert "human" in (rubric_grade.failure_reason or "")


def test_compare_is_matched_and_reports_family_not_prompt_multiplication():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    cases = [case for case in suite.cases if case.evaluation.method == "exact_json"][:4]
    left = [grade_attempt(c, _attempt(c.case_id, json.dumps(c.evaluation.reference_answer), model="left")) for c in cases]
    right = [grade_attempt(c, _attempt(c.case_id, "{}", model="right")) for c in cases]
    result = compare_grades(left, right, cases=cases)

    assert result.matched_cases == 4
    assert result.by_domain[cases[0].domain]["n"] == 1
    assert result.family_counts[cases[0].family_id] == 1
    # Comparison is defined as left-minus-right.
    assert result.observed_difference == 1.0
    assert result.independence_unit == "family_id"


def test_regression_report_keeps_unknown_values_unknown():
    baseline = {"communication": {"score": 0.9, "n": 4}, "calendar": {"score": None, "n": 0}}
    current = {"communication": {"score": 0.5, "n": 4}, "calendar": {"score": 1.0, "n": 1}}
    report = regression_report(baseline, current, minimum_sample_size=2)
    assert report["regressions"][0]["dimension"] == "communication"
    assert report["regressions"][0]["delta"] == pytest.approx(-0.4)
    assert report["changes"]["calendar"]["delta"] is None
    assert report["limitations"]
