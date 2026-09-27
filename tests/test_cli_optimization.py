"""Tests for offline optimization CLI commands.

Covers the full offline optimization operator loop:
- telemetry import (TelemetryBatchV1 parsing, quarantine, candidate creation, deduplication)
- candidates list, approve, and reject with lifecycle auditing
- reward compute for telemetry and benchmark runs
- router dataset (joining observations and rewards, line-aware splits, persistence)
- router train (LinUCB fitting, candidate creation in TRAINED state)
- router evaluate (validation off-policy evaluation, OPE metrics reporting)
- verify promotion gates (fail closed on missing/absent benchmark evidence)
- policy approve (strict VERIFIED requirement, named actor and reason)
- artifact keygen, export, and verification (cryptographic Ed25519 signing and tamper detection)
- preservation of existing pilot paid gates and draft router recommendations
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from model_lab.cli import build_parser, main
from model_lab.schema_registry import VERIFICATION_SCHEMA_VERSION
from model_lab.schemas import utc_now
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore
from model_lab.telemetry.synthetic import generate_batch


def test_cli_subparsers_registered() -> None:
    """Verify all required optimization commands are registered in build_parser."""
    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0].choices

    assert "telemetry" in subparsers
    assert "candidates" in subparsers
    assert "reward" in subparsers
    assert "router" in subparsers
    assert "verify" in subparsers
    assert "policy" in subparsers
    assert "artifact" in subparsers

    # Router subcommands
    router_subs = subparsers["router"]._subparsers._group_actions[0].choices
    assert "recommend" in router_subs
    assert "dataset" in router_subs
    assert "train" in router_subs
    assert "evaluate" in router_subs

    # Candidates subcommands
    candidates_subs = subparsers["candidates"]._subparsers._group_actions[0].choices
    assert "list" in candidates_subs
    assert "approve" in candidates_subs
    assert "reject" in candidates_subs

    # Artifact subcommands
    artifact_subs = subparsers["artifact"]._subparsers._group_actions[0].choices
    assert "keygen" in artifact_subs
    assert "export" in artifact_subs
    assert "verify" in artifact_subs


def test_complete_telemetry_optimization_cli_loop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """End-to-end test of the real offline optimization operator loop via CLI."""
    db_path = str(tmp_path / "optimization.sqlite3")

    # 1. Deterministic synthetic telemetry fixture
    batch = generate_batch(seed=42, runs=30)
    batch_file = tmp_path / "telemetry_batch.json"
    batch_file.write_text(json.dumps(batch, indent=2), encoding="utf-8")

    # 2. Telemetry import
    capsys.readouterr()
    exit_code = main(["telemetry", "import", str(batch_file), "--db", db_path])
    assert exit_code == 0
    import_out = json.loads(capsys.readouterr().out)
    assert import_out["import_id"].startswith("imp-")
    assert import_out["accepted"] > 0
    assert import_out["observations"] > 0
    assert import_out["candidates"] > 0
    assert import_out["status"] in ("imported", "duplicate")
    import_id = import_out["import_id"]

    # 3. Candidates list
    capsys.readouterr()
    assert main(["candidates", "list", "--db", db_path]) == 0
    cands_out = json.loads(capsys.readouterr().out)
    assert len(cands_out) >= 2
    assert all(c["state"] == "VALIDATED" for c in cands_out)

    cid_approve = cands_out[0]["candidate_id"]
    cid_reject = cands_out[1]["candidate_id"]

    # 4. Candidates approve
    capsys.readouterr()
    assert main([
        "candidates", "approve", cid_approve, "--db", db_path,
        "--role", "TRAIN_ONLY",
        "--actor", "lead_curator",
        "--reason", "high novelty and clean execution",
    ]) == 0
    app_out = json.loads(capsys.readouterr().out)
    assert app_out["to_state"] == "TRAIN_ONLY"
    assert app_out["actor"] == "lead_curator"

    # 5. Candidates reject
    capsys.readouterr()
    assert main([
        "candidates", "reject", cid_reject, "--db", db_path,
        "--actor", "lead_curator",
        "--reason", "redundant trajectory",
    ]) == 0
    rej_out = json.loads(capsys.readouterr().out)
    assert rej_out["to_state"] == "REJECTED"

    # Verify state filter on candidates list
    capsys.readouterr()
    assert main(["candidates", "list", "--db", db_path, "--state", "TRAIN_ONLY"]) == 0
    train_only_cands = json.loads(capsys.readouterr().out)
    assert len(train_only_cands) == 1
    assert train_only_cands[0]["candidate_id"] == cid_approve

    # 6. Reward compute for single run and all runs
    single_run_id = batch["runs"][0]["run_id"]
    capsys.readouterr()
    assert main(["reward", "compute", single_run_id, "--db", db_path]) == 0
    rew_single = json.loads(capsys.readouterr().out)
    assert rew_single["reward_id"].startswith("rew-")
    assert rew_single["subject_id"] == single_run_id
    assert rew_single["scalar"] is not None

    # Compute rewards for the entire import batch
    capsys.readouterr()
    assert main(["reward", "compute", import_id, "--db", db_path]) == 0
    rew_import = json.loads(capsys.readouterr().out)
    assert rew_import["computed"] > 0

    # 7. Router dataset generation
    capsys.readouterr()
    assert main(["router", "dataset", "--db", db_path, "--seed", "42"]) == 0
    ds_out = json.loads(capsys.readouterr().out)
    assert ds_out["dataset_id"].startswith("ds-")
    assert ds_out["checksum"] is not None
    assert ds_out["counts_by_split"]["train"] > 0
    assert ds_out["counts_by_split"]["validation"] > 0
    dataset_id = ds_out["dataset_id"]

    # 8. Router train
    capsys.readouterr()
    assert main(["router", "train", dataset_id, "--db", db_path, "--seed", "42"]) == 0
    train_out = json.loads(capsys.readouterr().out)
    assert train_out["candidate_id"].startswith("pol-")
    assert train_out["algorithm"] == "linucb"
    assert len(train_out["actions"]) > 0
    candidate_id = train_out["candidate_id"]

    # Verify candidate is in TRAINED state
    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        assert evidence.state("policy_candidate", candidate_id) == "TRAINED"
    finally:
        store.close()

    # 9. Router evaluate (validation OPE)
    capsys.readouterr()
    assert main(["router", "evaluate", candidate_id, "--db", db_path]) == 0
    eval_out = json.loads(capsys.readouterr().out)
    assert eval_out["candidate_id"] == candidate_id
    assert eval_out["split"] == "validation"
    assert eval_out["n"] > 0
    assert "ips" in eval_out
    assert "snips" in eval_out
    assert "dr" in eval_out


def test_candidates_approval_and_rejection_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify operator approval and rejection require non-blank actor and reason."""
    db_path = str(tmp_path / "candidates.sqlite3")
    batch = generate_batch(seed=10, runs=5)
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")
    assert main(["telemetry", "import", str(batch_file), "--db", db_path]) == 0

    capsys.readouterr()
    assert main(["candidates", "list", "--db", db_path]) == 0
    cid = json.loads(capsys.readouterr().out)[0]["candidate_id"]

    # Blank actor
    assert main(["candidates", "approve", cid, "--db", db_path, "--actor", "  ", "--reason", "valid"]) == 2
    # Blank reason
    assert main(["candidates", "approve", cid, "--db", db_path, "--actor", "operator", "--reason", ""]) == 2
    # Blank actor on reject
    assert main(["candidates", "reject", cid, "--db", db_path, "--actor", "", "--reason", "rejected"]) == 2
    # Blank reason on reject
    assert main(["candidates", "reject", cid, "--db", db_path, "--actor", "operator", "--reason", "   "]) == 2


def test_verify_refuses_missing_benchmark_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify promotion verifier fails closed when benchmark runs are absent or empty."""
    db_path = str(tmp_path / "verify.sqlite3")
    batch = generate_batch(seed=11, runs=10)
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")
    assert main(["telemetry", "import", str(batch_file), "--db", db_path]) == 0
    assert main(["reward", "compute", "all", "--db", db_path]) == 0
    assert main(["router", "dataset", "--db", db_path, "--seed", "11"]) == 0

    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        ds = evidence.list("datasets")[0]
        dataset_id = ds["dataset_id"]
    finally:
        store.close()

    capsys.readouterr()
    assert main(["router", "train", dataset_id, "--db", db_path, "--seed", "11"]) == 0
    candidate_id = json.loads(capsys.readouterr().out)["candidate_id"]

    # 1. Missing --benchmark-runs argument entirely fails closed
    assert main(["verify", candidate_id, "--db", db_path]) == 2

    # 2. Empty JSON mapping fails closed
    assert main(["verify", candidate_id, "--db", db_path, "--benchmark-runs", "{}"]) == 2

    # 3. Referencing nonexistent run IDs fails closed
    assert main(["verify", candidate_id, "--db", db_path, "--benchmark-runs", '{"sim/cheap": "run-does-not-exist"}']) == 2


def test_policy_approve_controls(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify policy approval requires a VERIFIED candidate and non-blank actor/reason."""
    db_path = str(tmp_path / "policy.sqlite3")
    batch = generate_batch(seed=12, runs=10)
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")
    assert main(["telemetry", "import", str(batch_file), "--db", db_path]) == 0
    assert main(["reward", "compute", "all", "--db", db_path]) == 0
    assert main(["router", "dataset", "--db", db_path, "--seed", "12"]) == 0

    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        dataset_id = evidence.list("datasets")[0]["dataset_id"]
    finally:
        store.close()

    capsys.readouterr()
    assert main(["router", "train", dataset_id, "--db", db_path, "--seed", "12"]) == 0
    candidate_id = json.loads(capsys.readouterr().out)["candidate_id"]

    # In TRAINED state, policy approve must fail closed (cannot jump TRAINED -> APPROVED)
    assert main(["policy", "approve", candidate_id, "--db", db_path, "--actor", "operator-1", "--reason", "testing"]) == 2

    # Blank actor / reason validation
    assert main(["policy", "approve", candidate_id, "--db", db_path, "--actor", "   ", "--reason", "testing"]) == 2
    assert main(["policy", "approve", candidate_id, "--db", db_path, "--actor", "operator-1", "--reason", ""]) == 2

    # Transition to VERIFIED and verify approval succeeds
    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        evidence.transition("policy_candidate", candidate_id, "VERIFIED", actor="verifier", reason="verified mock gates")
    finally:
        store.close()

    capsys.readouterr()
    assert main(["policy", "approve", candidate_id, "--db", db_path, "--actor", "lead-operator", "--reason", "production readiness check passed"]) == 0
    app_out = json.loads(capsys.readouterr().out)
    assert app_out["to_state"] == "APPROVED"
    assert app_out["actor"] == "lead-operator"


def test_artifact_keygen_export_and_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Ed25519 key generation, bundle export, and signature/tamper verification."""
    # Deterministic git state for bundle export
    clean_git = {
        "commit": "777a9b42e86c4732cdcfaba9d4dad06c4496bf65",
        "dirty": False,
        "branch": "main",
    }
    monkeypatch.setattr("model_lab.cli.commands.git_state", lambda: dict(clean_git))

    db_path = str(tmp_path / "artifacts.sqlite3")
    key_path = tmp_path / "signing_key.hex"
    out_dir = tmp_path / "exported_bundles"

    # 1. Keygen
    capsys.readouterr()
    assert main(["artifact", "keygen", "--path", str(key_path)]) == 0
    key_out = json.loads(capsys.readouterr().out)
    assert key_path.is_file()
    assert len(key_out["public_key"]) == 64
    assert len(key_out["key_id"]) == 16
    public_key = key_out["public_key"]

    # Re-generating to existing path must fail closed
    assert main(["artifact", "keygen", "--path", str(key_path)]) == 2

    # 2. Setup trained, verified, and approved candidate in SQLite
    batch = generate_batch(seed=15, runs=10)
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")
    assert main(["telemetry", "import", str(batch_file), "--db", db_path]) == 0
    assert main(["reward", "compute", "all", "--db", db_path]) == 0
    assert main(["router", "dataset", "--db", db_path, "--seed", "15"]) == 0

    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        dataset_id = evidence.list("datasets")[0]["dataset_id"]
    finally:
        store.close()

    capsys.readouterr()
    assert main(["router", "train", dataset_id, "--db", db_path, "--seed", "15"]) == 0
    candidate_id = json.loads(capsys.readouterr().out)["candidate_id"]

    # Exporting unapproved candidate must fail closed
    assert main(["artifact", "export", candidate_id, "--db", db_path, "--out", str(out_dir), "--key-path", str(key_path), "--actor", "operator-1"]) == 2

    # Add passing verification report and transition to APPROVED
    store = SQLiteStore(db_path)
    try:
        evidence = EvidenceStore(store)
        ver_report = {
            "report_id": "ver-test-report-01",
            "policy_candidate_id": candidate_id,
            "schema_version": VERIFICATION_SCHEMA_VERSION,
            "passed": True,
            "evidence_class": "SIMULATED",
            "evaluation_run_ids": ["run-bench-01"],
            "human_review_run_ids": [],
            "grader_versions": {"core_grader": "v1.0.0"},
            "created_at": utc_now(),
        }
        evidence.append("verification_reports", "ver-test-report-01", ver_report)
        evidence.transition("policy_candidate", candidate_id, "VERIFIED", actor="verifier", reason="gates passed")
        evidence.transition("policy_candidate", candidate_id, "APPROVED", actor="operator-lead", reason="approved for export")
    finally:
        store.close()

    # Exporting with blank actor must fail closed
    assert main(["artifact", "export", candidate_id, "--db", db_path, "--out", str(out_dir), "--key-path", str(key_path), "--actor", "  "]) == 2

    # 3. Export signed bundle
    capsys.readouterr()
    assert main([
        "artifact", "export", candidate_id, "--db", db_path,
        "--out", str(out_dir),
        "--key-path", str(key_path),
        "--actor", "operator-lead",
    ]) == 0
    export_out = json.loads(capsys.readouterr().out)
    bundle_id = export_out["bundle_id"]
    bundle_path = out_dir / bundle_id
    assert bundle_path.is_dir()
    assert (bundle_path / "checksums.json").is_file()
    assert (bundle_path / "signature.sig").is_file()
    assert (bundle_path / "manifest.json").is_file()

    # 4. Verify bundle with trusted key
    capsys.readouterr()
    assert main(["artifact", "verify", str(bundle_path), "--trusted-public-key", public_key]) == 0
    verify_valid = json.loads(capsys.readouterr().out)
    assert verify_valid["verified"] is True

    # 5. Verify bundle rejects untrusted key
    untrusted_key = "00" * 32
    capsys.readouterr()
    assert main(["artifact", "verify", str(bundle_path), "--trusted-public-key", untrusted_key]) == 2
    verify_untrusted = json.loads(capsys.readouterr().out)
    assert verify_untrusted["verified"] is False
    assert any("signing key is not trusted" in err for err in verify_untrusted["errors"])

    # 6. Verify bundle rejects tampering
    policy_file = bundle_path / "routing_policy.json"
    os.chmod(policy_file, 0o644)
    policy_file.write_bytes(policy_file.read_bytes() + b"\n/* tampered */")

    capsys.readouterr()
    assert main(["artifact", "verify", str(bundle_path), "--trusted-public-key", public_key]) == 2
    verify_tampered = json.loads(capsys.readouterr().out)
    assert verify_tampered["verified"] is False
    assert any("checksum mismatch" in err for err in verify_tampered["errors"])


def test_pilot_paid_gate_and_router_recommend_unmodified(tmp_path: Path) -> None:
    """Ensure existing pilot paid execution gate and router recommend stay intact."""
    # Pilot run requires explicit --allow-paid authorization
    plan_path = tmp_path / "test_plan.json"
    assert main([
        "plan",
        "--suite", "benchmarks/seed_cases.jsonl",
        "--models", "synthetic-v1",
        "--repeats", "1",
        "--out", str(plan_path),
    ]) == 0

    assert main(["pilot", "run", "--plan", str(plan_path)]) == 2

    # Router recommend requires explicit --draft acknowledgement
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"routing_recommendations": []}), encoding="utf-8")
    assert main(["router", "recommend", "--summary", str(summary_path)]) == 2
