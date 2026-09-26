import json

from model_lab.analysis import compare_grades
from model_lab.grading import grade_attempt, grade_exact_json
from model_lab.routing import draft_recommendations
from model_lab.benchmark import load_suite
from model_lab.schemas import Attempt, AttemptStatus, Grade, ModelConfig, utc_now


ROOT = __import__("pathlib").Path(__file__).parents[1]


def _attempt(case_id, model="m", text="{}", status=AttemptStatus.SUCCESS):
    return Attempt(
        attempt_id=f"{model}-{case_id}-{status.value}", run_id="run", logical_request_id=f"logical-{case_id}",
        case_id=case_id, model_config=ModelConfig(provider="fixture", model=model), prompt_hash="c" * 16,
        response_text=text, status=status, started_at=utc_now(),
    )


def _grade(case_id, model, score, attempt_id=None):
    return Grade(
        grade_id=f"grade-{attempt_id or model + case_id}", attempt_id=attempt_id or f"{model}-{case_id}",
        grader_id="exact_json", grader_version="1", method="exact_json", passed=score == 1,
        score=score, failure_reason=None if score is not None else "unknown",
        evidence={"case_id": case_id, "model": {"model": model}}, created_at=utc_now(),
    )


def test_exact_json_is_strict_about_types_large_integers_and_non_json_constants():
    assert grade_exact_json('{"ok": true}', {"ok": 1}, attempt_id="bool").passed is False
    huge = 9007199254740993
    assert grade_exact_json(json.dumps(huge), huge, attempt_id="huge").passed is True
    assert grade_exact_json(json.dumps(huge - 1), huge, attempt_id="huge-wrong").passed is False
    malformed = grade_exact_json("{\"value\": NaN}", {"value": None}, attempt_id="nan")
    assert malformed.passed is False and malformed.score == 0 and "valid JSON" in (malformed.failure_reason or "")


def test_failed_attempt_grade_retains_case_model_and_attempt_conditions():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    case = suite.cases[0]
    grade = grade_attempt(case, _attempt(case.case_id, model="provider-model", status=AttemptStatus.PROVIDER_FAILURE, text=None))
    assert grade.passed is None and grade.score is None
    assert grade.attempt_id == f"provider-model-{case.case_id}-provider_failure"
    assert grade.evidence["case_id"] == case.case_id
    assert grade.evidence["model"]["model"] == "provider-model"
    assert grade.evidence["evaluation_method"] == case.evaluation.method


def test_duplicate_pairs_are_excluded_and_reported_instead_of_last_write_wins():
    cases = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[:2]
    left = [_grade(cases[0].case_id, "left", 1.0), _grade(cases[0].case_id, "left", 0.0, "left-repeat"),
            _grade(cases[1].case_id, "left", 1.0)]
    right = [_grade(cases[0].case_id, "right", 1.0), _grade(cases[1].case_id, "right", 1.0)]
    result = compare_grades(left, right, cases=cases)
    assert result.duplicate_case_ids == (cases[0].case_id,)
    assert result.matched_cases == 1
    assert result.scored_pairs == 1
    assert "Duplicate case observations" in " ".join(result.limitations)


def test_recommendation_fails_closed_for_unknown_critical_condition_and_synthetic_evidence():
    cases = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[:10]
    left = [_grade(case.case_id, "left", 1.0) for case in cases]
    right = [_grade(case.case_id, "right", 0.0) for case in cases]
    comparison = compare_grades(left, right, cases=cases)
    unknown = draft_recommendations(comparison, cases=cases, eligibility={"left": True, "right": True})
    assert unknown and all(item["eligibility"] is False for item in unknown)
    assert any("Critical-failure" in limitation for limitation in unknown[0]["limitations"])
    synthetic = draft_recommendations(comparison, cases=cases, eligibility={"left": True, "right": True}, synthetic=True,
                                      critical_failures={"all": True}, condition_eligibility={"text": True})
    assert synthetic and all(item["eligibility"] is False for item in synthetic)
