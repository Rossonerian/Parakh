import pytest

from model_lab.benchmark import load_suite
from model_lab.errors import ValidationError
from model_lab.review import adjudication_summary, export_blind_review, import_blind_reviews, review_bindings
from model_lab.schemas import Attempt, AttemptStatus, ModelConfig, utc_now

ROOT = __import__("pathlib").Path(__file__).parents[1]

def _attempt(case_id, attempt_id="attempt-1"):
    return Attempt(attempt_id=attempt_id, run_id="run-real", logical_request_id="logical-1", case_id=case_id, model_config=ModelConfig(provider="fake", model="m"), prompt_hash="a" * 16, response_text="candidate", status=AttemptStatus.SUCCESS, started_at=utc_now())

def test_binding_round_trip_and_reviewer_specific_ids():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    attempt = _attempt(case.case_id)
    row = export_blind_review([attempt])[0]
    binding = review_bindings([attempt])
    records = [dict(row, decision="accept", reviewer_pseudonym="r1"), dict(row, decision="reject", reviewer_pseudonym="r2")]
    reviews = import_blind_reviews(records, expected_labels=binding)
    assert reviews[0].attempt_id == attempt.attempt_id and reviews[0].review_id != reviews[1].review_id
    summary = adjudication_summary(reviews)
    assert summary["conflict_count"] == 1 and summary["grades_created"] is False

def test_tampered_or_unbound_review_rejected():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    attempt = _attempt(case.case_id)
    row = dict(export_blind_review([attempt])[0], decision="accept", reviewer_pseudonym="r1")
    with pytest.raises(ValidationError, match="bindings are required"):
        import_blind_reviews([row])
    with pytest.raises(ValidationError, match="case_id"):
        import_blind_reviews([dict(row, case_id="tampered")], expected_labels=review_bindings([attempt]))
