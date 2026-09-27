"""Comprehensive unit and integration tests for preference extraction, classification, and export."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from model_lab.errors import ValidationError
from model_lab.preferences import (
    classify,
    export_approved,
    extract_pairs,
    readiness,
    review,
)
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord, parse_batch
from model_lab.telemetry.synthetic import generate_batch


@pytest.fixture
def base_run() -> RunRecord:
    batch = generate_batch(seed=123, runs=1)
    parsed = parse_batch(batch)
    return parsed.valid[0]


def test_classify_intent_change_and_non_trainable(base_run):
    # feedback_type == "intent_change" -> changed_intent
    fb_intent = {"feedback_id": "fb_1", "feedback_type": "intent_change", "created_at": "2026-09-27T00:00:00Z"}
    cl_intent = classify(fb_intent, base_run)
    assert cl_intent.category == "changed_intent"
    assert cl_intent.confidence >= 0.85

    # same_request is False -> changed_intent
    fb_diff_req = {"feedback_id": "fb_2", "feedback_type": "edit", "same_request": False, "created_at": "2026-09-27T00:00:00Z"}
    cl_diff = classify(fb_diff_req, base_run)
    assert cl_diff.category == "changed_intent"

    # hint style -> style_preference
    fb_style = {"feedback_id": "fb_3", "feedback_type": "edit", "correction_kind_hint": "style", "created_at": "2026-09-27T00:00:00Z"}
    cl_style = classify(fb_style, base_run)
    assert cl_style.category == "style_preference"

    # hint schedule -> schedule_detail_change
    fb_sched = {"feedback_id": "fb_3b", "feedback_type": "edit", "correction_kind_hint": "schedule", "created_at": "2026-09-27T00:00:00Z"}
    cl_sched = classify(fb_sched, base_run)
    assert cl_sched.category == "schedule_detail_change"


def test_classify_trainable_and_confidence_modifiers(base_run):
    # hint factual -> factual_correction
    fb_factual = {
        "feedback_id": "fb_4",
        "feedback_type": "edit",
        "correction_kind_hint": "factual",
        "minutes_after_output": 75,  # context drift -0.2
        "created_at": "2026-09-27T00:00:00Z",
    }
    cl_factual = classify(fb_factual, base_run)
    assert cl_factual.category == "factual_correction"
    assert cl_factual.confidence == pytest.approx(0.75 - 0.2, abs=0.01)

    # repair with run failures -> execution_repair (+0.1)
    run_with_failures = replace(
        base_run,
        validation_events=({"validator": "schema", "passed": False},),
    )
    fb_repair = {
        "feedback_id": "fb_5",
        "feedback_type": "edit",
        "correction_kind_hint": "repair",
        "created_at": "2026-09-27T00:00:00Z",
    }
    cl_repair = classify(fb_repair, run_with_failures)
    assert cl_repair.category == "execution_repair"
    assert cl_repair.confidence == pytest.approx(0.75 + 0.1, abs=0.01)

    # high correction distance -> suspicious of intent change (-0.15)
    fb_dist = {
        "feedback_id": "fb_5b",
        "feedback_type": "edit",
        "correction_kind_hint": "factual",
        "correction_distance": 0.85,
        "created_at": "2026-09-27T00:00:00Z",
    }
    cl_dist = classify(fb_dist, base_run)
    assert cl_dist.confidence == pytest.approx(0.75 - 0.15, abs=0.01)

    # Ambiguous when no hint and no evidence -> confidence <= 0.4
    fb_ambiguous = {"feedback_id": "fb_6", "feedback_type": "edit", "created_at": "2026-09-27T00:00:00Z"}
    cl_ambig = classify(fb_ambiguous, base_run)
    assert cl_ambig.category == "ambiguous"
    assert cl_ambig.confidence <= 0.4


def test_extract_pairs_lifecycle_and_privacy(base_run, tmp_path: Path):
    store = SQLiteStore(tmp_path / "pref.db")
    evidence = EvidenceStore(store)

    run = replace(
        base_run,
        feedback=(
            # High confidence trainable -> PROPOSED
            {
                "feedback_id": "fb_prop",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "Paris is the capital",
                "original_value": "Lyon is the capital",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Intent change -> EXCLUDED
            {
                "feedback_id": "fb_intent",
                "feedback_type": "intent_change",
                "corrected_value": "Write a poem instead",
                "original_value": "Here is an essay",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Ambiguous -> NEEDS_REVIEW
            {
                "feedback_id": "fb_ambig",
                "feedback_type": "edit",
                "corrected_value": "Some adjustment",
                "original_value": "Previous response",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Privacy leak (Bearer token) -> EXCLUDED with reason privacy
            {
                "feedback_id": "fb_priv_bearer",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "Bearer abcdef1234567890",
                "original_value": "old text",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Privacy leak (sk- token) -> EXCLUDED
            {
                "feedback_id": "fb_priv_sk",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "sk-proj12345678abcdef",
                "original_value": "old text",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Privacy leak (email) -> EXCLUDED
            {
                "feedback_id": "fb_priv_email",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "Contact alice@example.com for details",
                "original_value": "old text",
                "created_at": "2026-09-27T00:00:00Z",
            },
            # Missing chosen text -> EXCLUDED
            {
                "feedback_id": "fb_missing_chosen",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "",
                "original_value": "valid old text",
                "created_at": "2026-09-27T00:00:00Z",
            },
        ),
    )

    extracted = extract_pairs(evidence, [run], min_confidence=0.7)
    assert len(extracted) == 7

    states = evidence.states("preference_pair")
    pair_prop = next(p for p in extracted if p["feedback_id"] == "fb_prop")
    pair_intent = next(p for p in extracted if p["feedback_id"] == "fb_intent")
    pair_ambig = next(p for p in extracted if p["feedback_id"] == "fb_ambig")
    pair_priv_bearer = next(p for p in extracted if p["feedback_id"] == "fb_priv_bearer")
    pair_priv_sk = next(p for p in extracted if p["feedback_id"] == "fb_priv_sk")
    pair_priv_email = next(p for p in extracted if p["feedback_id"] == "fb_priv_email")
    pair_no_chosen = next(p for p in extracted if p["feedback_id"] == "fb_missing_chosen")

    assert states[pair_prop["pair_id"]] == "PROPOSED"
    assert states[pair_intent["pair_id"]] == "EXCLUDED"
    assert states[pair_ambig["pair_id"]] == "NEEDS_REVIEW"
    assert states[pair_priv_bearer["pair_id"]] == "EXCLUDED"
    assert states[pair_priv_sk["pair_id"]] == "EXCLUDED"
    assert states[pair_priv_email["pair_id"]] == "EXCLUDED"
    assert states[pair_no_chosen["pair_id"]] == "EXCLUDED"
    assert "missing_chosen_text" in pair_no_chosen["reason"]
    store.close()


def test_review_flow_and_transitions(base_run, tmp_path: Path):
    store = SQLiteStore(tmp_path / "review.db")
    evidence = EvidenceStore(store)

    run = replace(
        base_run,
        feedback=(
            {
                "feedback_id": "fb_rev",
                "feedback_type": "edit",
                "corrected_value": "Better value",
                "original_value": "Old value",
                "created_at": "2026-09-27T00:00:00Z",
            },
        ),
    )

    extracted = extract_pairs(evidence, [run])
    pair_id = extracted[0]["pair_id"]
    assert evidence.state("preference_pair", pair_id) == "NEEDS_REVIEW"

    # NEEDS_REVIEW -> PROPOSED
    review(evidence, pair_id, "propose", actor="reviewer_1", reason="verified correction")
    assert evidence.state("preference_pair", pair_id) == "PROPOSED"

    # PROPOSED -> APPROVED
    review(evidence, pair_id, "approve", actor="reviewer_2", reason="quality approved")
    assert evidence.state("preference_pair", pair_id) == "APPROVED"

    # APPROVED -> REJECTED
    review(evidence, pair_id, "reject", actor="reviewer_3", reason="found defect")
    assert evidence.state("preference_pair", pair_id) == "REJECTED"

    # Terminal state rejection
    with pytest.raises(ValidationError):
        review(evidence, pair_id, "approve", actor="reviewer_4", reason="cannot re-approve")
    store.close()


def test_export_and_readiness_gate(base_run, tmp_path: Path):
    store = SQLiteStore(tmp_path / "export.db")
    evidence = EvidenceStore(store)

    run = replace(
        base_run,
        feedback=(
            {
                "feedback_id": "fb_1",
                "feedback_type": "edit",
                "correction_kind_hint": "factual",
                "corrected_value": "Paris",
                "original_value": "Berlin",
                "created_at": "2026-09-27T00:00:00Z",
            },
            {
                "feedback_id": "fb_2",
                "feedback_type": "intent_change",
                "corrected_value": "Poem",
                "original_value": "Essay",
                "created_at": "2026-09-27T00:00:00Z",
            },
        ),
    )

    extracted = extract_pairs(evidence, [run], min_confidence=0.7)
    pair_1_id = next(p for p in extracted if p["feedback_id"] == "fb_1")["pair_id"]

    # Approve pair 1
    review(evidence, pair_1_id, "approve", actor="lead", reason="golden pair")

    # Check export: only APPROVED exported
    export_file = tmp_path / "approved.jsonl"
    count = export_approved(evidence, export_file)
    assert count == 1

    lines = [json.loads(line) for line in export_file.read_text(encoding="utf-8").strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["pair_id"] == pair_1_id
    assert lines[0]["approval_state"] == "APPROVED"
    assert lines[0]["chosen"] == "Paris"
    assert lines[0]["rejected"] == "Berlin"
    assert set(lines[0].keys()) == {
        "pair_id",
        "prompt_or_context_ref",
        "chosen",
        "rejected",
        "confidence",
        "reason",
        "source_run_id",
        "approval_state",
    }

    # Readiness check: approved_count (1) < 500 and missing target -> justified False
    gate_no_target = readiness(evidence, min_pairs=500, trainable_target=None)
    assert gate_no_target["justified"] is False
    assert "missing_trainable_target" in gate_no_target["reasons"]
    assert any("below_minimum" in r for r in gate_no_target["reasons"])

    # Readiness check: satisfied when threshold lowered and target provided
    gate_ok = readiness(evidence, min_pairs=1, trainable_target="karmi-dpo-v1")
    assert gate_ok["justified"] is True
    assert gate_ok["approved_count"] == 1
    assert gate_ok["has_trainable_target"] is True
    assert gate_ok["reasons"] == []
    store.close()
