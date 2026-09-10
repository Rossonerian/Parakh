import json

from model_lab.analysis import compare_grades
from model_lab.grading import grade_attempt
from model_lab.review import export_blind_review, import_blind_reviews
from model_lab.routing import draft_recommendations
from model_lab.benchmark import load_suite
from model_lab.schemas import Attempt, ModelConfig, AttemptStatus, utc_now


ROOT = __import__("pathlib").Path(__file__).parents[1]


def _attempt(case_id, model, text):
    return Attempt(
        attempt_id=f"{model}-{case_id}", run_id=f"run-{model}", logical_request_id=f"logical-{case_id}",
        case_id=case_id, model_config=ModelConfig(provider="fake", model=model), prompt_hash="b" * 16,
        response_text=text, status=AttemptStatus.SUCCESS, started_at=utc_now(),
    )


def test_blind_review_export_hides_provider_and_model_and_imports_decision():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    case = suite.cases[0]
    attempt = _attempt(case.case_id, "secret-model", "candidate text")
    exported = export_blind_review([attempt], include_prompt=False)
    assert len(exported) == 1
    serialized = json.dumps(exported[0], sort_keys=True).lower()
    assert "secret-model" not in serialized and "fake" not in serialized
    assert exported[0]["blind_label"].startswith("candidate-")
    reviews = import_blind_reviews([dict(exported[0], decision="accept", score=1, reviewer_pseudonym="reviewer-1")])
    assert reviews[0].case_id == case.case_id
    assert reviews[0].decision == "accept"


def test_router_draft_is_evidence_bound_and_marks_synthetic_limitations():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    cases = [case for case in suite.cases if case.evaluation.method == "exact_json"][:2]
    good = [grade_attempt(c, _attempt(c.case_id, "good", json.dumps(c.evaluation.reference_answer))) for c in cases]
    weak = [grade_attempt(c, _attempt(c.case_id, "weak", "{}")) for c in cases]
    comparison = compare_grades(good, weak, cases=cases)
    recommendations = draft_recommendations(comparison, cases=cases, eligibility={"good": True, "weak": True}, synthetic=True)
    assert recommendations
    assert recommendations[0]["candidate_model"] == "good"
    assert recommendations[0]["evidence_ids"]
    assert recommendations[0]["limitations"]
    assert recommendations[0]["synthetic"] is True
