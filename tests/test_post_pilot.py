import json
from pathlib import Path

import pytest

from model_lab.benchmark import load_suite
from model_lab.errors import ValidationError
from model_lab.grading import grade_attempt
from model_lab.post_pilot import (
    calibration_selection_report,
    consume_holdout_evaluation,
    critical_failure_report,
    export_stratified_calibration_review,
    reconcile_provider_usage,
    router_replay_shadow,
)
from model_lab.schemas import Attempt, AttemptStatus, ModelConfig, utc_now


ROOT = Path(__file__).parents[1]


def _attempt(case_id: str, attempt_id: str, *, status=AttemptStatus.SUCCESS, text: str | None = "answer", cost: int | None = None) -> Attempt:
    return Attempt(
        attempt_id=attempt_id, run_id="run-pilot", logical_request_id=f"logical-{attempt_id}", case_id=case_id,
        model_config=ModelConfig(provider="fake", model="candidate-a"), prompt_hash="a" * 16,
        response_text=text, status=status, started_at=utc_now(), cost_minor=cost, currency="USD" if cost is not None else None,
    )


def test_reconciliation_preserves_unknowns_and_flags_duplicates():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    attempts = [_attempt(suite.cases[0].case_id, "attempt-1", cost=10), _attempt(suite.cases[1].case_id, "attempt-2", cost=None)]
    report = reconcile_provider_usage(attempts, [{"attempt_id": "attempt-1", "cost_minor": 12, "currency": "USD"}, {"attempt_id": "attempt-1", "cost_minor": 12, "currency": "USD"}])
    assert report["provider_cost_minor"] == 24
    assert report["local_cost_minor"] is None
    assert report["cost_delta_minor"] is None
    assert report["missing_attempt_ids"] == ["attempt-2"]
    assert report["duplicate_provider_attempt_ids"] == ["attempt-1"]


def test_critical_failure_report_is_protected_and_observable_only():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    case = next(case for case in suite.cases if case.evaluation.method == "exact_json")
    attempt = _attempt(case.case_id, "attempt-fail", status=AttemptStatus.TIMEOUT, text=None)
    grade = grade_attempt(case, attempt)
    report = critical_failure_report([case], [attempt], [grade])
    serialized = json.dumps(report, sort_keys=True)
    assert report["critical_failure_count"] == 1
    assert report["protected_oracle_included"] is False
    assert "reference_answer" not in serialized
    assert "attempt_status:timeout" in serialized


def test_stratified_calibration_export_hides_candidate_identity():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    calibration = [case for case in suite.cases if case.split == "calibration"]
    attempts = [_attempt(case.case_id, f"attempt-{case.case_id}") for case in calibration[:4]]
    report = export_stratified_calibration_review(suite.cases, attempts, sample_size=3)
    assert report["status"] == "ready"
    assert report["selected_count"] == 3
    serialized = json.dumps(report["rows"], sort_keys=True).lower()
    assert "candidate-a" not in serialized and "provider" not in serialized and "model" not in serialized
    assert report["candidate_identity_hidden"] is True


def test_calibration_selection_does_not_auto_select():
    report = calibration_selection_report([{"blind_label": "candidate-x", "decision": "accept"}], policy_candidates=["policy-a", "policy-b"])
    assert report["selected_policy_id"] is None
    assert report["selection_status"] == "owner_review_required"


def test_holdout_guard_is_one_time_and_rejects_tuning(tmp_path: Path):
    lock = tmp_path / "holdout.lock.json"
    with pytest.raises(ValidationError, match="cannot be used for tuning"):
        consume_holdout_evaluation(lock, policy_hash="p", config_hash="c", holdout_case_ids=["h1"], tuning=True)
    result = consume_holdout_evaluation(lock, policy_hash="p", config_hash="c", holdout_case_ids=["h1"])
    assert result["status"] == "consumed"
    assert json.loads(lock.read_text(encoding="utf-8"))["policy_hash"] == "p"
    with pytest.raises(ValidationError, match="already been consumed"):
        consume_holdout_evaluation(lock, policy_hash="p", config_hash="c", holdout_case_ids=["h1"])


def test_router_shadow_replay_does_not_mutate_application_config():
    config = {"router": {"active": "baseline"}}
    report = router_replay_shadow([{"candidate_model": "candidate-a", "draft_only": True}], observed_case_ids=["case-2", "case-1"], application_config=config)
    assert report["observed_case_ids"] == ["case-1", "case-2"]
    assert report["activation_performed"] is False
    assert report["application_config_changed"] is False
    assert config == {"router": {"active": "baseline"}}
