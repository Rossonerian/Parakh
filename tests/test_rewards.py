"""Comprehensive unit and integration tests for reward engine and trajectory grading."""

from dataclasses import replace
from pathlib import Path

import pytest

from model_lab.rewards import (
    RewardConfig,
    grade_trajectory,
    normalize_cost,
    normalize_latency,
    persist,
    persist_trajectory_grade,
    reward_for_attempt,
    reward_for_run,
    rubric_from_reviews,
    user_signal,
)
from model_lab.schema_registry import REWARD_SCHEMA_VERSION, TRAJECTORY_GRADE_SCHEMA_VERSION
from model_lab.schemas import Attempt, AttemptStatus, Grade, HumanReview, ModelConfig, stable_json
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord, parse_batch
from model_lab.telemetry.synthetic import generate_batch


@pytest.fixture
def sample_run() -> RunRecord:
    batch = generate_batch(seed=42, runs=1)
    parsed = parse_batch(batch)
    assert len(parsed.valid) >= 1
    return parsed.valid[0]


def test_reward_config_defaults_and_hash():
    config = RewardConfig()
    assert config.weights["quality"] == 1.0
    assert config.weights["cost"] == 0.2
    assert config.weights["latency"] == 0.1
    assert config.weights["tool_failure"] == 0.2
    assert config.weights["retry"] == 0.1
    assert config.quality_weights["deterministic"] == 0.6
    assert config.quality_weights["rubric"] == 0.25
    assert config.quality_weights["user"] == 0.15
    assert config.cost_envelope_per_request["ananta"] == 0.002
    assert config.cost_envelope_per_request["yanta"] == 0.01
    assert config.cost_envelope_per_request["trika"] == 0.05
    assert config.cost_envelope_per_request["part"] == 0.10
    assert config.default_latency_slo_ms == 8000
    assert config.cost_cap == 1.5
    assert config.latency_cap == 1.5
    assert config.critical_failure_reward == -1.0
    assert config.provisional is True
    assert "tier envelopes are placeholders" in config.note
    assert len(config.config_hash()) == 64

    # from_dict and to_dict
    d = config.to_dict()
    reconstructed = RewardConfig.from_dict(d)
    assert reconstructed.config_hash() == config.config_hash()


def test_reward_determinism_and_evidence_persistence(sample_run, tmp_path: Path):
    config = RewardConfig()
    rec1 = reward_for_run(sample_run, config)
    rec2 = reward_for_run(sample_run, config)

    # Identical record byte-equality
    assert stable_json(rec1.to_dict()) == stable_json(rec2.to_dict())
    assert rec1.schema_version == REWARD_SCHEMA_VERSION
    assert rec1.config_hash == config.config_hash()

    # Evidence store persistence
    store = SQLiteStore(tmp_path / "evidence.db")
    evidence = EvidenceStore(store)
    assert persist(evidence, rec1) is True
    # Idempotent re-append
    assert persist(evidence, rec1) is False

    retrieved = evidence.get("rewards", rec1.reward_id)
    assert retrieved["subject_type"] == "telemetry_run"
    assert retrieved["subject_id"] == sample_run.run_id
    assert retrieved["schema_version"] == REWARD_SCHEMA_VERSION
    assert retrieved["config_hash"] == config.config_hash()
    assert retrieved["components"]["deterministic"] == rec1.components.deterministic
    store.close()


def test_deterministic_dominance_and_user_signals(sample_run):
    config = RewardConfig()

    # D=1 with weak negative user signal (e.g. retry / abandon) still yields Q >= 0.7
    run_d1_abandon = replace(
        sample_run,
        outcome={**sample_run.outcome, "completed": True, "structured_output_valid": True, "user_abandon_signal": True},
        tool_events=tuple({"schema_valid": True, "execution_success": True} for _ in range(3)),
    )
    rec = reward_for_run(run_d1_abandon, config)
    assert rec.components.deterministic == 1.0
    assert rec.components.user_signal == 0.0
    assert rec.quality is not None and rec.quality >= 0.7

    # Inactivity (no signals) gives U is None (never positive)
    run_inactive = replace(
        sample_run,
        outcome={k: v for k, v in sample_run.outcome.items() if not k.startswith("user_")},
        feedback=(),
    )
    u_val, u_strength = user_signal(run_inactive)
    assert u_val is None and u_strength is None
    rec_inactive = reward_for_run(run_inactive, config)
    assert rec_inactive.components.user_signal is None

    # changed_intent correction does not lower reward vs no-correction
    run_changed_intent = replace(
        run_inactive,
        outcome={**run_inactive.outcome, "completed": True, "user_correction_signal": True},
        feedback=({"feedback_id": "fb1", "feedback_type": "intent_change", "created_at": "2026-09-27T00:00:00Z"},),
    )
    rec_intent = reward_for_run(run_changed_intent, config, correction_category="changed_intent")
    rec_no_corr = reward_for_run(run_inactive, config)
    assert rec_intent.components.user_signal is None
    assert rec_intent.quality == rec_no_corr.quality
    assert rec_intent.scalar == rec_no_corr.scalar


def test_unknown_cost_and_non_usd_currencies(sample_run):
    config = RewardConfig()

    # Unknown cost -> penalty term is 0, confidence reduced (multiplied by 0.8), metadata notes missing cost
    run_no_cost = replace(
        sample_run,
        outcome={**sample_run.outcome, "final_cost": None, "currency": None},
    )
    rec_no_cost = reward_for_run(run_no_cost, config)
    assert rec_no_cost.components.cost_normalized is None
    assert "cost" in rec_no_cost.metadata["missing"]
    assert rec_no_cost.confidence < 1.0

    # Non-USD currency -> never convert, treated as missing cost
    run_eur = replace(
        sample_run,
        outcome={**sample_run.outcome, "final_cost": 0.05, "currency": "EUR"},
    )
    assert normalize_cost(0.05, "EUR", "ananta", config) is None
    rec_eur = reward_for_run(run_eur, config)
    assert rec_eur.components.cost_normalized is None
    assert "cost" in rec_eur.metadata["missing"]


def test_unknown_latency(sample_run):
    config = RewardConfig()
    assert normalize_latency(None, None, config) is None

    run_no_lat = replace(
        sample_run,
        outcome={**sample_run.outcome, "final_latency_ms": None},
    )
    rec = reward_for_run(run_no_lat, config)
    assert rec.components.latency_normalized is None
    assert "latency" in rec.metadata["missing"]


def test_critical_failure_enforces_safety_reward(sample_run):
    config = RewardConfig(critical_failure_reward=-1.0)
    run_crit = replace(
        sample_run,
        outcome={**sample_run.outcome, "completed": True, "critical_failure": True},
    )
    rec = reward_for_run(run_crit, config)
    assert rec.components.safety_violation is True
    assert rec.scalar == -1.0


def test_structured_output_failure_and_retry_penalties(sample_run):
    config = RewardConfig()

    # Structured output required and invalid -> tool failure penalty capped at 1.0
    run_bad_schema = replace(
        sample_run,
        routing_context={**sample_run.routing_context, "requires_structured_output": True},
        outcome={**sample_run.outcome, "structured_output_valid": False, "retry_count": 2},
        tool_events=(),
    )
    rec = reward_for_run(run_bad_schema, config)
    assert rec.components.tool_failure_penalty == 1.0
    assert rec.components.retry_penalty == pytest.approx(2.0 / 3.0)
    assert rec.components.recovery_success is True  # completed=True after retry > 0


def test_no_quality_signal_yields_none_scalar(sample_run):
    config = RewardConfig()
    run_no_quality = replace(
        sample_run,
        routing_context={**sample_run.routing_context, "requires_structured_output": False},
        outcome={"completed": None, "structured_output_valid": None},
        tool_events=(),
        feedback=(),
    )
    rec = reward_for_run(run_no_quality, config)
    assert rec.quality is None
    assert rec.scalar is None
    assert rec.excluded_reason == "no_quality_signal"
    assert rec.confidence == 0.0


def test_reward_for_benchmark_attempt_with_rubric():
    config = RewardConfig()
    attempt = Attempt(
        attempt_id="att_001",
        run_id="run_001",
        logical_request_id="req_001",
        case_id="case_001",
        model_config=ModelConfig(provider="sim", model="sim/flagship"),
        prompt_hash="a" * 64,
        response_text="answer",
        status=AttemptStatus.SUCCESS,
        started_at="2026-09-27T00:00:00Z",
        completion_latency_ms=4000.0,
        cost_minor=5,
        currency="USD",
    )
    grade = Grade(
        grade_id="grd_001",
        attempt_id="att_001",
        grader_id="grader_auto",
        grader_version="v1",
        method="exact_json",
        passed=True,
        score=1.0,
        failure_reason=None,
        evidence={"details": "matched"},
        created_at="2026-09-27T00:01:00Z",
    )
    reviews = [
        HumanReview(
            review_id="rev_001",
            run_id="run_001",
            case_id="case_001",
            blind_label="A",
            reviewer_pseudonym="r1",
            decision="accept",
            score=0.9,
            notes=None,
            confidence=0.95,
            created_at="2026-09-27T00:02:00Z",
        ),
        HumanReview(
            review_id="rev_002",
            run_id="run_001",
            case_id="case_001",
            blind_label="A",
            reviewer_pseudonym="r2",
            decision="tie",
            score=0.5,
            notes=None,
            confidence=0.8,
            created_at="2026-09-27T00:02:00Z",
        ),
    ]

    h_score, h_strength = rubric_from_reviews(reviews)
    assert h_score == 0.9  # tie excluded
    assert h_strength == "medium"

    rec = reward_for_attempt(attempt, grade, reviews, config)
    assert rec.subject_type == "benchmark_attempt"
    assert rec.subject_id == "att_001"
    assert rec.components.deterministic == 1.0
    assert rec.components.rubric == 0.9
    assert rec.quality is not None and rec.quality > 0.9
    assert rec.scalar is not None

    # Benchmark attempt with abstained grade and no reviews
    grade_abstain = Grade(
        grade_id="grd_002",
        attempt_id="att_001",
        grader_id="grader_auto",
        grader_version="v1",
        method="exact_json",
        passed=None,
        score=None,
        failure_reason="abstained",
        evidence={},
        created_at="2026-09-27T00:01:00Z",
    )
    rec_abstain = reward_for_attempt(attempt, grade_abstain, None, config)
    assert rec_abstain.quality is None
    assert rec_abstain.scalar is None
    assert rec_abstain.excluded_reason == "no_quality_signal"


def test_trajectory_grading_dimensions_and_loop_detection(sample_run, tmp_path: Path):
    # Test None when memory signal absent
    run_no_mem = replace(
        sample_run,
        routing_context={**sample_run.routing_context, "requires_memory": False},
        validation_events=tuple(v for v in sample_run.validation_events if "memory" not in str(v.get("validator", "")).lower()),
    )
    tg_no_mem = grade_trajectory(run_no_mem)
    assert tg_no_mem["state_retention"]["value"] is None

    # Test loop detection with 3 identical tool errors
    run_loop = replace(
        sample_run,
        outcome={**sample_run.outcome, "completed": False, "retry_count": 3},
        tool_events=(
            {"tool_name": "calc", "error_class": "ZeroDivisionError", "schema_valid": True, "execution_success": False},
            {"tool_name": "calc", "error_class": "ZeroDivisionError", "schema_valid": True, "execution_success": False},
            {"tool_name": "calc", "error_class": "ZeroDivisionError", "schema_valid": True, "execution_success": False},
        ),
    )
    tg_loop = grade_trajectory(run_loop)
    assert tg_loop["error_recovery"]["value"] == 0.0
    assert any("loop_detected=True" in ev for ev in tg_loop["error_recovery"]["evidence"])

    # Test persistence of trajectory grade
    store = SQLiteStore(tmp_path / "traj.db")
    evidence = EvidenceStore(store)
    assert persist_trajectory_grade(evidence, run_loop.run_id, tg_loop) is True
    assert evidence.exists("trajectory_grades", f"tg-{run_loop.run_id}-{TRAJECTORY_GRADE_SCHEMA_VERSION}")
    store.close()
