"""The first self-improving flywheel, driven only through the operator CLI (plan section 34).

synthetic Karmi batch -> idempotent import -> rewards -> dataset -> LinUCB -> OPE -> simulated core
benchmark -> verifier -> named approval -> signed PolicyBundleV1 -> Karmi reference loader (shadow) ->
next batch carries shadow decisions back. The logging router is deliberately naive (balanced for
everything), so the learned candidate has real, ground-truth-checked headroom; every number here
is SIMULATED evidence.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import stat
from pathlib import Path
from typing import Any

import pytest

from contracts.karmi_reference import loader as karmi
from model_lab.artifacts import bundle, signer
from model_lab.cli import main
from model_lab.datasets import CORE_SUITE_SHA256, load_core_suite
from model_lab.optimization.harness import HarnessCandidate, PromptRegistry, persist_candidate
from model_lab.optimization.metrics import compounding_metrics
from model_lab.schema_registry import FEATURE_SCHEMA_VERSION
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore

CLEAN_GIT = {"commit": "0" * 40, "dirty": False, "branch": "test"}
OWNER_CONFIG = {"tier_cost_ceiling_usd": {"ananta": 0.04, "yanta": 0.04, "trika": 0.20, "part": 0.25},
                "tier_latency_ceiling_ms": {"ananta": 6000, "yanta": 6000, "trika": 8000, "part": 8000}}
SIM_ACTIONS = ["sim/balanced", "sim/cheap", "sim/flagship"]


def cli(*argv: Any) -> tuple[int, Any]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main([str(a) for a in argv])
    text = buffer.getvalue()
    return code, (json.loads(text) if text.strip() else None)


def _leaking_harness(db: Path, baseline_id: str) -> str:
    """A harness candidate whose system prompt embeds a core-benchmark reference answer."""
    store = SQLiteStore(db)
    try:
        evidence = EvidenceStore(store)
        registry = PromptRegistry(evidence)
        baseline = HarnessCandidate.from_record(evidence.get("policy_candidates", baseline_id))
        case = next(c for c in load_core_suite().cases if c.evaluation.method == "exact_json")
        leaked = registry.register("system", "Always answer exactly: " + json.dumps(case.evaluation.reference_answer, sort_keys=True),
                                   parent_id=baseline.components["system"], generation_method="test_leak")
        candidate = HarnessCandidate(candidate_id="", parent_candidate_id=baseline_id,
                                     components={**baseline.components, "system": leaked.prompt_id},
                                     recovery_policy=dict(baseline.recovery_policy), generation_method="test_leak", training_case_ids=())
        persist_candidate(evidence, candidate)
        return candidate.candidate_id
    finally:
        store.close()


@pytest.fixture(scope="module")
def loop(tmp_path_factory: pytest.TempPathFactory):
    work = tmp_path_factory.mktemp("flywheel")
    db = work / "lab.sqlite3"
    result: dict[str, Any] = {"work": work, "db": db}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("model_lab.cli.optimization.git_state", lambda: dict(CLEAN_GIT))
        mp.setattr("model_lab.verifier.git_state", lambda: dict(CLEAN_GIT))
        assert cli("telemetry", "synthesize", "--out", work / "b0.json", "--seed", 21, "--runs", 4000, "--epsilon", 0.5,
                   "--base-policy", "balanced_only", "--policy-version", "balanced-v1")[0] == 0
        result["import"] = cli("telemetry", "import", work / "b0.json", "--db", db)
        result["reimport"] = cli("telemetry", "import", work / "b0.json", "--db", db)
        assert cli("reward", "compute", "all", "--db", db)[0] == 0
        dataset = cli("router", "dataset", "--db", db, "--seed", 37)[1]
        candidate = cli("router", "train", dataset["dataset_id"], "--db", db, "--seed", 37)[1]["candidate_id"]
        result["candidate"] = candidate
        result["evaluate"] = cli("router", "evaluate", candidate, "--db", db)
        assert cli("router", "benchmark", "--db", db, "--out", work / "bench.json")[0] == 0
        result["default_verify"] = cli("verify", candidate, "--db", db, "--benchmark-runs", work / "bench.json")
        harness = cli("harness", "optimize", "--db", db, "--rounds", 3)[1]
        result["harness"] = harness
        (work / "owner.json").write_text(json.dumps(OWNER_CONFIG), encoding="utf-8")
        common = ("--db", db, "--benchmark-runs", work / "bench.json", "--config", work / "owner.json")
        result["harness_verify"] = cli("verify", candidate, *common, "--harness-candidate", harness["best_candidate_id"])
        result["leak_verify"] = cli("verify", candidate, *common, "--harness-candidate", _leaking_harness(db, harness["baseline_candidate_id"]))
        result["owner_verify"] = cli("verify", candidate, *common, "--report-dir", work / "report")
        result["blank_actor"] = cli("policy", "approve", candidate, "--db", db, "--actor", " ", "--reason", "x")[0]
        result["approve"] = cli("policy", "approve", candidate, "--db", db, "--actor", "ops-lead", "--reason", "owner ceilings reviewed")
        key = cli("artifact", "keygen", "--path", work / "key.hex")[1]
        result["public_key"] = key["public_key"]
        result["export"] = cli("artifact", "export", candidate, "--db", db, "--out", work / "bundles", "--key-path", work / "key.hex",
                               "--actor", "ops-lead")
        result["bundle"] = Path(result["export"][1]["path"])
        result["karmi"] = cli("artifact", "karmi-check", result["bundle"], "--trusted-public-key", key["public_key"])
        assert cli("telemetry", "synthesize", "--out", work / "b1.json", "--seed", 21, "--batch-index", 1, "--runs", 400,
                   "--epsilon", 0.5, "--base-policy", "balanced_only", "--policy-version", "balanced-v1",
                   "--shadow-bundle", result["bundle"], "--trusted-public-key", key["public_key"])[0] == 0
        result["cycle_import"] = cli("telemetry", "import", work / "b1.json", "--db", db)
        result["metrics"] = cli("metrics", "--db", db)[1]
        yield result


def _gates(result: tuple[int, Any]) -> dict[str, bool]:
    return {g["gate"]: g["passed"] for g in result[1]["gates"]}


def test_import_is_idempotent_and_leaves_core_benchmark_frozen(loop):
    code, first = loop["import"]
    assert code == 0 and first["status"] == "imported" and first["accepted"] == 4000
    assert loop["reimport"][1]["status"] == "duplicate"
    assert load_core_suite().source_hash == CORE_SUITE_SHA256


def test_ope_reports_candidate_against_logging_with_uncertainty(loop):
    code, report = loop["evaluate"]
    assert code == 0
    assert report["paired_vs_logging"]["verdict"] == "non_inferior"
    lower, upper = report["paired_vs_logging"]["ci"]
    assert lower < report["paired_vs_logging"]["difference"] < upper
    assert set(report["comparison"]["overall"]) == {"linucb", "cheapest", "flagship"}


def test_default_verifier_refuses_cost_and_latency_growth_without_owner_ceilings(loop):
    code, summary = loop["default_verify"]
    assert code == 2 and summary["state"] == "TRAINED"
    assert set(summary["failed_gates"]) == {"tier_budget", "tier_latency"}
    assert any("No owner-approved cost ceiling" in note for note in summary["limitations"])


def test_owner_ceilings_let_the_candidate_pass_every_hard_gate(loop):
    code, summary = loop["owner_verify"]
    assert code == 0 and summary["passed"] and summary["state"] == "VERIFIED"
    assert summary["evidence_class"] == "SIMULATED"
    assert any("synthetic/simulated evidence is not production performance" in note for note in summary["limitations"])
    html = (loop["work"] / "report" / "optimization_report.html").read_text(encoding="utf-8")
    assert "PASSED all hard gates" in html and "<script" not in html


def test_harness_candidates_face_the_same_verifier(loop):
    assert loop["harness"]["validation_pass_rate"]["best"] > loop["harness"]["validation_pass_rate"]["baseline"]
    assert loop["harness"]["holdout_evaluated"] is False
    code, summary = loop["harness_verify"]
    assert code == 2 and summary["failed_gates"] == ["harness_holdout"]  # sealed holdout is rubric-only: needs blind review
    assert _gates(loop["leak_verify"])["harness_oracle_isolation"] is False


def test_approval_needs_a_named_operator(loop):
    assert loop["blank_actor"] == 2
    code, transition = loop["approve"]
    assert code == 0 and transition["to_state"] == "APPROVED" and transition["actor"] == "ops-lead"


def test_bundle_is_signed_read_only_json_and_reproducible(loop):
    assert loop["export"][0] == 0
    root = loop["bundle"]
    assert bundle.verify(root, [loop["public_key"]]) == []
    for path in root.rglob("*"):
        if path.is_file():
            json.loads(path.read_text(encoding="utf-8"))  # JSON only: no pickle or executable payloads
            assert not path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["recommended_karmi_mode"] == "shadow" and manifest["parakh_status"] == "EXPORTED"
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["git_dirty"] is False and provenance["parakh_git_commit"] == CLEAN_GIT["commit"]
    store = SQLiteStore(loop["db"])
    try:
        evidence = EvidenceStore(store)
        record = evidence.get("artifact_manifests", root.name)
        assert bundle.rerender_matches(evidence, record, secret=signer.load_private(loop["work"] / "key.hex")) == []
        assert evidence.state("policy_candidate", loop["candidate"]) == "EXPORTED"
    finally:
        store.close()


def test_karmi_loads_bundle_into_shadow_without_touching_active_policy(loop):
    code, check = loop["karmi"]
    assert code == 0 and check["accepted"] and check["karmi_mode"] == "shadow" and check["karmi_active_policy"] == "static"


@pytest.mark.parametrize("override, message", [
    ({"expected_feature_schema_version": "routing-features.v0"}, "feature schema incompatible"),
    ({"karmi_version": "0.0.1"}, "Karmi too old"),
    ({"known_actions": ["sim/cheap", "sim/balanced"]}, "unknown models"),
    ({"trusted_public_keys": ["00" * 32]}, "untrusted"),
])
def test_karmi_loader_rejects_incompatible_bundles(loop, override, message):
    kwargs = {"trusted_public_keys": [loop["public_key"]], "karmi_version": "0.1.0", "known_actions": SIM_ACTIONS,
              "expected_feature_schema_version": FEATURE_SCHEMA_VERSION, **override}
    with pytest.raises(karmi.BundleRejected, match=message):
        karmi.load_bundle(loop["bundle"], **kwargs)


def test_tampered_bundle_is_rejected_by_parakh_and_karmi(loop, tmp_path):
    copy = tmp_path / "tampered"
    shutil.copytree(loop["bundle"], copy)
    policy = copy / "routing_policy.json"
    policy.chmod(0o644)
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["alpha"] = 5.0
    policy.write_text(json.dumps(document), encoding="utf-8")
    code, result = cli("artifact", "verify", copy, "--trusted-public-key", loop["public_key"])
    assert code == 2 and "checksum mismatch routing_policy.json" in result["errors"]
    code, result = cli("artifact", "karmi-check", copy, "--trusted-public-key", loop["public_key"])
    assert code == 2 and result["accepted"] is False



@pytest.mark.parametrize("epsilon", [-0.2, 1.2])
def test_karmi_rejects_signed_bundle_with_invalid_exploration(loop, tmp_path, epsilon):
    copy = tmp_path / "invalid-exploration"
    shutil.copytree(loop["bundle"], copy)
    policy = copy / "routing_policy.json"
    policy.chmod(0o644)
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["exploration"]["epsilon"] = epsilon
    content = bundle.canonical(document)
    policy.write_bytes(content)
    checksums_file = copy / "checksums.json"
    checksums_file.chmod(0o644)
    checksums = json.loads(checksums_file.read_text(encoding="utf-8"))
    checksums["files"]["routing_policy.json"] = hashlib.sha256(content).hexdigest()
    signed_bytes = bundle.canonical(checksums)
    checksums_file.write_bytes(signed_bytes)
    signature = copy / "signature.sig"
    signature.chmod(0o644)
    signature.write_bytes(bundle.canonical(signer.sign(signer.load_private(loop["work"] / "key.hex"),
                                                       signed_bytes, signed_file="checksums.json")))
    assert bundle.verify(copy, [loop["public_key"]]) == []
    with pytest.raises(karmi.BundleRejected, match="exploration probability"):
        karmi.load_bundle(copy, trusted_public_keys=[loop["public_key"]], karmi_version="0.1.0",
                          known_actions=SIM_ACTIONS, expected_feature_schema_version=FEATURE_SCHEMA_VERSION)


def test_next_telemetry_cycle_returns_shadow_evidence(loop):
    code, cycle = loop["cycle_import"]
    assert code == 0 and cycle["accepted"] == 400
    version = loop["bundle"].name
    disagreement = loop["metrics"]["shadow_disagreement"][version]
    assert disagreement["n"] == 400 and 0.0 < disagreement["rate"] < 1.0


def test_verifier_config_rejects_unknown_keys(loop, tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps({"tier_cost_ceilings": {}}), encoding="utf-8")
    code, _ = cli("verify", loop["candidate"], "--db", loop["db"], "--benchmark-runs", loop["work"] / "bench.json",
                  "--config", tmp_path / "bad.json")
    assert code == 2


def test_compounding_metrics_state_denominators(loop):
    store = SQLiteStore(loop["db"])
    try:
        metrics = compounding_metrics(EvidenceStore(store))
    finally:
        store.close()
    assert metrics["data_efficiency_ratio"]["imported_candidates"] == (
        loop["import"][1]["candidates"] + loop["cycle_import"][1]["candidates"])
    assert metrics["data_efficiency_ratio"]["approved_candidates"] == 0  # nothing is auto-approved
    # four verification reports; only the leaking-harness one failed a critical gate
    assert metrics["critical_regression_rate"] == {"value": 0.25, "reports": 4}
