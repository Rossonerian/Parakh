"""Fail-closed behavior of the offline optimization CLI (the full loop lives in test_flywheel.py)."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

from model_lab.cli import main
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.synthetic import generate_batch


def cli(*argv: Any) -> tuple[int, Any]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([str(a) for a in argv])
    text = buffer.getvalue()
    return code, (json.loads(text) if text.strip() else None)


@pytest.fixture
def imported(tmp_path: Path) -> Path:
    batch = generate_batch(seed=11, runs=60, faults={"missing_propensity": 2})
    (tmp_path / "batch.json").write_text(json.dumps(batch), encoding="utf-8")
    db = tmp_path / "lab.sqlite3"
    assert cli("telemetry", "import", tmp_path / "batch.json", "--db", db)[0] == 0
    return db


def test_candidate_promotion_is_explicit_audited_and_terminal(imported: Path):
    candidates = cli("candidates", "list", "--db", imported, "--state", "VALIDATED")[1]
    cid = candidates[0]["candidate_id"]
    assert all(c["state"] == "VALIDATED" for c in candidates)  # automated checks passed; nothing approved yet
    assert cli("candidates", "approve", cid, "--db", imported, "--role", "REGRESSION", "--actor", "  ", "--reason", "r")[0] == 2
    code, transition = cli("candidates", "approve", cid, "--db", imported, "--role", "REGRESSION", "--actor", "ops", "--reason", "novel failure")
    assert code == 0 and transition["to_state"] == "REGRESSION" and transition["actor"] == "ops"
    # a role is terminal: re-assigning requires a new candidate record
    assert cli("candidates", "approve", cid, "--db", imported, "--role", "TRAIN_ONLY", "--actor", "ops", "--reason", "r")[0] == 2
    status = cli("telemetry", "status", "--db", imported)[1]
    assert status[0]["quarantined"] == 2 and status[0]["quarantine_reasons"]


def test_quarantined_runs_never_receive_rewards(imported: Path):
    store = SQLiteStore(imported)
    try:
        quarantined = EvidenceStore(store).list("telemetry_records", status="quarantined")[0]["run_id"]
    finally:
        store.close()
    assert cli("reward", "compute", quarantined, "--db", imported)[0] == 2
    code, summary = cli("reward", "compute", "all", "--db", imported)
    assert code == 0 and summary["computed"] == 58


def test_verify_requires_graded_benchmark_evidence(imported: Path, tmp_path: Path):
    assert cli("reward", "compute", "all", "--db", imported)[0] == 0
    dataset = cli("router", "dataset", "--db", imported, "--seed", 1)[1]
    candidate = cli("router", "train", dataset["dataset_id"], "--db", imported, "--seed", 1)[1]["candidate_id"]
    assert cli("verify", candidate, "--db", imported, "--benchmark-runs", "{}")[0] == 2
    assert cli("verify", candidate, "--db", imported, "--benchmark-runs", '{"sim/cheap": "run-does-not-exist"}')[0] == 2
    store = SQLiteStore(imported)
    try:
        assert EvidenceStore(store).state("policy_candidate", candidate) == "TRAINED"
    finally:
        store.close()
    assert cli("policy", "approve", candidate, "--db", imported, "--actor", "ops", "--reason", "skip verification")[0] == 2
    assert cli("verify", candidate, "--db", tmp_path / "missing.sqlite3", "--benchmark-runs", '{"a": "b"}')[0] == 2


def test_simulated_benchmark_evidence_is_refused_for_real_models(tmp_path: Path):
    db = tmp_path / "real.sqlite3"
    store = SQLiteStore(db)
    try:
        EvidenceStore(store).append("telemetry_imports", "imp-real", {
            "import_id": "imp-real", "batch_id": "karmi-1", "batch_checksum": "x", "producer_repo": "kashyep-karmi",
            "model_registry": [{"provider": "acme", "model": "large", "model_version": "2026-09"}]})
    finally:
        store.close()
    assert cli("router", "benchmark", "--db", db)[0] == 2


def test_pilot_paid_gate_and_router_recommend_unmodified(tmp_path: Path):
    plan_path = tmp_path / "plan.json"
    assert main(["plan", "--suite", "benchmarks/seed_cases.jsonl", "--models", "synthetic-v1", "--repeats", "1", "--out", str(plan_path)]) == 0
    assert main(["pilot", "run", "--plan", str(plan_path)]) == 2
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"routing_recommendations": []}), encoding="utf-8")
    assert main(["router", "recommend", "--summary", str(summary_path)]) == 2
