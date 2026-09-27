"""Tests for candidate curation, novelty scoring, role assignment, and core benchmark immutability."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from model_lab.errors import IntegrityError, ValidationError
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore
from model_lab.telemetry.curation import approve, data_efficiency, list_candidates, reject
from model_lab.telemetry.importer import import_batch
from model_lab.telemetry.novelty import NoveltyContext, score
from model_lab.telemetry.schema import parse_batch
from model_lab.telemetry.synthetic import generate_batch


def test_novelty_scoring_bounds_and_comparison(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=50)
    import_batch(store, batch)

    evidence = EvidenceStore(store)
    ctx = NoveltyContext.from_store(evidence)
    parsed = parse_batch(batch)

    # Identical to history
    hist_run = parsed.valid[0]
    nov_hist = score(hist_run, ctx)
    assert 0.0 <= nov_hist.score <= 1.0
    assert all(0.0 <= v <= 1.0 for v in nov_hist.components.values())

    # Novel domain and failure
    novel_raw = copy.deepcopy(batch["runs"][0])
    novel_raw["run_id"] = "srun-novel-distinct"
    novel_raw["task_domain"] = "novel_unseen_domain"
    novel_raw["routing_context"]["task_domain"] = "novel_unseen_domain"
    novel_raw["attempts"][0]["error_type"] = "unseen_fatal_error"
    novel_raw["outcome"]["completed"] = False

    parsed_novel = parse_batch({**batch, "runs": [novel_raw]})
    nov_novel = score(parsed_novel.valid[0], ctx)
    assert 0.0 <= nov_novel.score <= 1.0
    assert all(0.0 <= v <= 1.0 for v in nov_novel.components.values())

    # Novel run must have higher score than run identical to history
    assert nov_novel.score > nov_hist.score


def test_curation_approval_requires_validated(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=10)
    import_batch(store, batch)
    evidence = EvidenceStore(store)

    validated_cands = list_candidates(evidence, state="VALIDATED")
    assert len(validated_cands) >= 2
    c_valid = validated_cands[0]["candidate_id"]
    c_to_reject = validated_cands[1]["candidate_id"]

    # Reject c_to_reject
    reject(evidence, c_to_reject, actor="reviewer", reason="not relevant")
    assert evidence.state("evaluation_candidate", c_to_reject) == "REJECTED"

    # Cannot approve rejected candidate
    with pytest.raises(ValidationError, match="approval requires VALIDATED"):
        approve(evidence, c_to_reject, "TRAIN_ONLY", actor="lead", reason="should fail")

    # Can approve validated candidate
    app_res = approve(evidence, c_valid, "REGRESSION", actor="lead", reason="good regression test")
    assert app_res["to_state"] == "REGRESSION"
    assert evidence.state("evaluation_candidate", c_valid) == "REGRESSION"


def test_curation_approval_atomic_sequence(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=5)
    import_batch(store, batch)
    evidence = EvidenceStore(store)

    cands = list_candidates(evidence, state="VALIDATED")
    assert len(cands) > 0
    cid = cands[0]["candidate_id"]

    # Approve into VALIDATION role
    approve(evidence, cid, "VALIDATION", actor="curator", reason="valid candidate for validation set")

    # Verify history has both transitions: VALIDATED -> APPROVED -> VALIDATION
    hist = evidence.history("evaluation_candidate", cid)
    states = [h["to_state"] for h in hist]
    assert "NEW" in states
    assert "VALIDATED" in states
    assert "APPROVED" in states
    assert "VALIDATION" in states

    # Invalid role raises ValidationError
    with pytest.raises(ValidationError, match="invalid candidate role"):
        approve(evidence, cid, "INVALID_ROLE", actor="curator", reason="should fail")


def test_curation_holdout_role_is_terminal(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=5)
    import_batch(store, batch)
    evidence = EvidenceStore(store)

    cands = list_candidates(evidence, state="VALIDATED")
    cid = cands[0]["candidate_id"]

    # Approve into HOLDOUT
    approve(evidence, cid, "HOLDOUT", actor="verifier", reason="assigned to secret holdout")
    assert evidence.state("evaluation_candidate", cid) == "HOLDOUT"

    # HOLDOUT cannot later become TRAIN_ONLY via approve (requires VALIDATED)
    with pytest.raises(ValidationError, match="approval requires VALIDATED"):
        approve(evidence, cid, "TRAIN_ONLY", actor="curator", reason="reassign attempt")

    # Direct transition from HOLDOUT to TRAIN_ONLY is forbidden by state machine
    with pytest.raises(IntegrityError, match="transition HOLDOUT -> TRAIN_ONLY is not allowed"):
        evidence.transition("evaluation_candidate", cid, "TRAIN_ONLY", actor="curator", reason="force reassign")


def test_curation_list_candidates_filters(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=10)
    import_batch(store, batch)
    evidence = EvidenceStore(store)

    all_cands = list_candidates(evidence)
    assert len(all_cands) > 0
    for c in all_cands:
        assert "state" in c

    cid = all_cands[0]["candidate_id"]
    approve(evidence, cid, "ADVERSARIAL", actor="curator", reason="adversarial case")

    adv_cands = list_candidates(evidence, state="ADVERSARIAL")
    assert len(adv_cands) == 1
    assert adv_cands[0]["candidate_id"] == cid
    assert adv_cands[0]["state"] == "ADVERSARIAL"


def test_data_efficiency_metrics(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=15)
    res = import_batch(store, batch)
    evidence = EvidenceStore(store)

    eff1 = data_efficiency(evidence)
    assert eff1["imported_runs"] == res.accepted
    assert eff1["imported_candidates"] == res.candidates
    assert eff1["approved"] == 0
    assert eff1["ratio"] == 0.0

    cands = list_candidates(evidence, state="VALIDATED")
    assert len(cands) >= 2
    approve(evidence, cands[0]["candidate_id"], "TRAIN_ONLY", actor="lead", reason="train")
    approve(evidence, cands[1]["candidate_id"], "HOLDOUT", actor="lead", reason="holdout")

    eff2 = data_efficiency(evidence)
    assert eff2["approved"] == 2
    assert eff2["ratio"] == (2 / res.candidates)
    assert f"2 approved out of {res.candidates} imported candidates" in eff2["note"]


def test_core_benchmark_file_immutability(tmp_path: Path) -> None:
    benchmark_path = Path("benchmarks/seed_cases.jsonl")
    initial_sha = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()

    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=10)
    import_batch(store, batch)
    evidence = EvidenceStore(store)

    cands = list_candidates(evidence, state="VALIDATED")
    if cands:
        approve(evidence, cands[0]["candidate_id"], "REGRESSION", actor="lead", reason="approve")

    after_sha = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()
    assert initial_sha == after_sha, "Core benchmark seed_cases.jsonl was unexpectedly modified!"
