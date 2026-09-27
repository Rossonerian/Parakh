"""Contracts shared by every optimization module, plus P0 invariants they rely on."""

import copy
import shutil
import sqlite3
from pathlib import Path

import pytest

import model_lab.pilot as pilot
from model_lab import datasets
from model_lab.artifacts import ed25519
from model_lab.errors import IntegrityError, PilotBlockedError
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import TelemetryBatchError, parse_batch
from model_lab.telemetry.synthetic import MODELS, eligible_actions, expected_outcome, generate_batch

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_batches_are_deterministic_and_parse_cleanly():
    first, second = generate_batch(seed=3, runs=50), generate_batch(seed=3, runs=50)
    assert first == second
    parsed = parse_batch(first)
    assert len(parsed.valid) == 50 and not parsed.invalid
    for run in parsed.valid:
        assert run.live_decision.action in run.live_decision.eligible_models
        assert 0 < run.live_decision.selection_probability <= 1


def test_record_faults_are_isolated_with_reason_codes_not_coerced():
    batch = generate_batch(seed=4, runs=40, faults={"missing_propensity": 2, "bad_context": 1, "ineligible_choice": 1, "duplicate_run": 1})
    parsed = parse_batch(batch)
    reasons = sorted(r for invalid in parsed.invalid for r in invalid.reasons)
    assert reasons.count("decisions[0].missing_selection_probability") == 2
    assert "routing_context.ratio_out_of_range" in reasons
    assert "decisions[0].selected_not_eligible" in reasons
    assert "run.duplicate_run_id_in_batch" in reasons
    assert len(parsed.valid) + len(parsed.invalid) == len(batch["runs"])


@pytest.mark.parametrize("mutate", [
    lambda b: b.update(schema="TelemetryBatchV2"),
    lambda b: b.update(schema_version="2.0.0"),
    lambda b: b.pop("batch_id"),
    lambda b: b.update(model_registry=[]),
    lambda b: b.update(producer={"repo": "kashyep-karmi"}),
])
def test_unusable_envelopes_reject_the_whole_batch(mutate):
    batch = generate_batch(seed=5, runs=3)
    mutate(batch)
    with pytest.raises(TelemetryBatchError):
        parse_batch(batch)


def test_probability_of_zero_or_above_one_is_not_valid_propensity():
    batch = generate_batch(seed=6, runs=2)
    batch["runs"][0]["decisions"][0]["selection_probability"] = 0
    batch["runs"][1]["decisions"][0]["selection_probability"] = 1.5
    assert {r for i in parse_batch(batch).invalid for r in i.reasons} == {"decisions[0].invalid_selection_probability"}


def test_evidence_is_idempotent_append_only_and_lifecycle_is_state_machined(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite3")
    evidence = EvidenceStore(store)
    assert evidence.append("rewards", "r1", {"subject_type": "run", "subject_id": "s1", "schema_version": "reward.v1", "scalar": 0.5})
    assert not evidence.append("rewards", "r1", {"subject_type": "run", "subject_id": "s1", "schema_version": "reward.v1", "scalar": 0.5})
    with pytest.raises(IntegrityError):
        evidence.append("rewards", "r1", {"subject_type": "run", "subject_id": "s1", "schema_version": "reward.v1", "scalar": 0.9})
    assert evidence.list("rewards", subject_id="s1")[0]["scalar"] == 0.5
    for statement in ("UPDATE rewards SET record_json = '{}'", "DELETE FROM rewards"):
        with pytest.raises(sqlite3.DatabaseError, match="immutable evidence"):
            store.connection.execute(statement)
    evidence.transition("evaluation_candidate", "c1", "NEW", actor="importer", reason="imported")
    with pytest.raises(IntegrityError):
        evidence.transition("evaluation_candidate", "c1", "HOLDOUT", actor="op", reason="skip approval")
    evidence.transition("evaluation_candidate", "c1", "VALIDATED", actor="importer", reason="privacy ok")
    evidence.transition("evaluation_candidate", "c1", "APPROVED", actor="operator", reason="reviewed")
    evidence.transition("evaluation_candidate", "c1", "HOLDOUT", actor="operator", reason="sealed")
    with pytest.raises(IntegrityError):
        evidence.transition("evaluation_candidate", "c1", "TRAIN_ONLY", actor="operator", reason="leak holdout into training")
    assert [h["to_state"] for h in evidence.history("evaluation_candidate", "c1")] == ["NEW", "VALIDATED", "APPROVED", "HOLDOUT"]
    assert evidence.states("evaluation_candidate") == {"c1": "HOLDOUT"}
    with pytest.raises(sqlite3.DatabaseError, match="immutable evidence"):
        store.connection.execute("DELETE FROM state_transitions")
    store.close()


def test_core_benchmark_is_frozen_and_roles_follow_splits(tmp_path):
    suite = datasets.load_core_suite()
    assert len(suite.cases) == 60 and len({c.domain for c in suite.cases}) == 15
    roles = [datasets.role_of(c) for c in suite.cases]
    assert (roles.count("train"), roles.count("validation"), roles.count("holdout")) == (36, 12, 12)
    records = datasets.core_case_records(suite)
    assert all(r.approval_state == "FROZEN" and r.lineage["suite_sha256"] == datasets.CORE_SUITE_SHA256 for r in records)
    tampered = tmp_path / "seed_cases.jsonl"
    shutil.copy(datasets.CORE_SUITE_PATH, tampered)
    tampered.write_bytes(tampered.read_bytes() + b"\n")
    with pytest.raises(IntegrityError, match="frozen"):
        datasets.load_core_suite(tampered)


def test_optimizers_cannot_request_holdout():
    suite = datasets.load_core_suite()
    assert all(datasets.role_of(c) != "holdout" for c in datasets.optimizer_cases(suite, ("train", "validation")))
    with pytest.raises(IntegrityError):
        datasets.optimizer_cases(suite, ("train", "holdout"))
    assert len(datasets.holdout_cases(suite)) == 12


def test_ed25519_matches_rfc8032_vectors_and_rejects_tampering():
    vectors = [
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ]
    for secret, public, message, signature in vectors:
        secret, public, message, signature = map(bytes.fromhex, (secret, public, message, signature))
        assert ed25519.public_key(secret) == public
        assert ed25519.sign(secret, message) == signature
        assert ed25519.verify(public, message, signature)
        assert not ed25519.verify(public, message + b"!", signature)
        assert not ed25519.verify(public, message, signature[:-1] + bytes([signature[-1] ^ 1]))


def test_synthetic_environment_truth_respects_eligibility_and_skill():
    context = {"tier": "part", "task_domain": "tabular_analysis", "estimated_input_tokens": 40_000, "requires_tools": True,
               "requires_structured_output": True}
    assert eligible_actions({**context, "tier": "ananta"}) == ("sim/balanced",)
    success = {m.action: expected_outcome(context, m.action)["success_probability"] for m in MODELS}
    assert success["sim/flagship"] > success["sim/balanced"] > success["sim/cheap"]


def test_live_pilot_runner_enforces_concurrency_ceiling(monkeypatch):
    """P0: concurrency ceiling holds even after authorization succeeds."""
    monkeypatch.setattr(pilot, "require_dispatch_authorization", lambda *a, **k: None)
    plan = {"immutable": True, "execution": {"concurrency": 2, "retry_limit": 0, "repeats": 1}}
    with pytest.raises(PilotBlockedError, match="concurrency=1"):
        pilot.run_authorized_immutable_pilot(plan, suite_path=datasets.CORE_SUITE_PATH, output_dir="unused",
                                             source_manifest_path="unused", constraint_map_path="unused")


def test_parse_batch_never_mutates_source():
    batch = generate_batch(seed=8, runs=5, faults={"bad_context": 1})
    before = copy.deepcopy(batch)
    parse_batch(batch)
    assert batch == before


def _contract(name):
    import json
    import sys
    sys.path.insert(0, str(ROOT / "contracts"))
    import schema_check
    return schema_check, json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))


def test_published_telemetry_schema_accepts_fixture_and_rejects_missing_propensity():
    import json
    schema_check, schema = _contract("telemetry_batch_v1.schema.json")
    fixture = json.loads((ROOT / "contracts/fixtures/telemetry_batch_v1.sample.json").read_text(encoding="utf-8"))
    assert schema_check.errors(fixture, schema) == []
    assert parse_batch(fixture).invalid == ()
    del fixture["runs"][0]["decisions"][0]["selection_probability"]
    assert any("selection_probability" in e for e in schema_check.errors(fixture, schema))


def test_feature_vectors_are_deterministic_bounded_and_text_free():
    from model_lab.optimization.router.features import extract, feature_schema
    schema = feature_schema()
    context = parse_batch(generate_batch(seed=9, runs=1)).valid[0].routing_context
    vector = extract(context)
    assert vector == extract(dict(context)) and len(vector) == schema["dimension"] == 34
    assert all(0.0 <= v <= 1.0 for v in vector) and vector[0] == 1.0
    assert sum(vector[1:6]) == 1.0 and sum(vector[6:22]) == 1.0  # exactly one tier and one domain bucket
    assert extract({**context, "task_domain": "unknown-karmi-domain"})[21] == 1.0
    from model_lab.telemetry.schema import CONTEXT_FIELDS, OPTIONAL_CONTEXT_FIELDS
    assert {f["source"] for f in schema["features"] if "source" in f} <= set(CONTEXT_FIELDS) | set(OPTIONAL_CONTEXT_FIELDS)
    assert feature_schema()["schema_id"] == schema["schema_id"]
