import json
import hashlib
from pathlib import Path

import pytest

from model_lab.cli import main
from model_lab.constraints import evaluate_constraints, file_sha256, load_constraint_map
from model_lab.operator_input import build_immutable_plan, load_operator_input
from model_lab.pilot import PilotBlockedError, dispatch_preview, require_dispatch_authorization
from tests.test_operator_input import complete_input


ROOT = Path(__file__).parents[1]
SUITE = ROOT / "benchmarks/seed_cases.jsonl"
CONSTRAINTS = ROOT / "docs/live_pilots/router-constraint-map-v0.2.0.json"
TEMPLATE = ROOT / "docs/live_pilots/operator-input.template.yaml"
MANIFEST = ROOT / "docs/product_sources/SOURCE_MANIFEST.json"


def test_imported_product_sources_match_manifest_hashes():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["import_status"] == "verified"
    assert manifest["ambiguity"]["status"] == "none"
    for name in ("PRD", "Architecture", "Design", "Tier_Entitlements"):
        record = manifest["documents"][name]
        source = ROOT / record["imported_path"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record["source_sha256"]


def test_imported_constraint_map_has_citations_and_owner_blockers():
    value = load_constraint_map(CONSTRAINTS)
    evaluation = evaluate_constraints(value)
    assert evaluation["evaluated"] >= 10
    assert "entitlement.canonical_ids" in evaluation["satisfied"]
    assert "owner.pricing_quotas_provider_allowlist" in evaluation["blocking"]
    assert not evaluation["activation_ready"]
    for constraint in value["constraints"]:
        assert constraint["citations"]
        assert all(len(item["source_sha256"]) == 64 for item in constraint["citations"])


def test_constraint_map_rejects_a_citation_not_bound_to_imported_source(tmp_path: Path):
    value = json.loads(CONSTRAINTS.read_text(encoding="utf-8"))
    value["constraints"][0]["citations"][0]["source_sha256"] = "0" * 64
    altered = tmp_path / "altered-map.json"
    altered.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(Exception, match="citation does not match source manifest"):
        load_constraint_map(altered)


def test_router_draft_refuses_activation_when_product_constraints_unresolved(tmp_path: Path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"routing_recommendations": [{"candidate_model": "synthetic", "synthetic": True}]}), encoding="utf-8")
    output = tmp_path / "router.json"
    assert main(["router", "recommend", "--summary", str(summary), "--draft", "--constraint-map", str(CONSTRAINTS), "--out", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["activation_ready"] is False
    assert report["production_config_changed"] is False
    assert report["constraint_evaluation"]["blocking"]


def test_operator_input_validation_and_immutable_plan_cli(tmp_path: Path):
    assert main(["pilot", "validate-input", "--input", str(TEMPLATE), "--suite", str(SUITE)]) == 2
    operator_file = tmp_path / "operator.json"
    operator_file.write_text(json.dumps(complete_input()), encoding="utf-8")
    plan_file = tmp_path / "pilot-plan.json"
    assert main([
        "pilot", "validate-input", "--input", str(operator_file), "--suite", str(SUITE),
    ]) == 0
    assert main([
        "pilot", "plan", "--operator-input", str(operator_file), "--suite", str(SUITE),
        "--constraint-map", str(CONSTRAINTS), "--out", str(plan_file),
    ]) == 0
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    assert plan["immutable"] is True
    assert plan["bounds"]["base_calls"] == 216
    assert plan["source_hash"]
    assert plan["constraint_hash"]


def test_valid_frozen_plan_prints_dispatch_evidence_but_no_dispatch_without_allow_paid():
    plan = build_immutable_plan(
        complete_input(), suite_path=SUITE, source_hash="a" * 64,
        constraint_hash="b" * 64, created_at="2026-09-11T10:00:00+00:00",
    )
    preview = dispatch_preview(plan)
    assert preview["base_calls"] == 216
    assert preview["maximum_calls"] == 432
    assert preview["judge_enabled"] is False
    assert preview["red_team_enabled"] is False
    assert preview["dispatch_performed"] is False
    with pytest.raises(PilotBlockedError, match="allow_paid"):
        require_dispatch_authorization(plan, allow_paid=False)


def test_tampered_immutable_plan_is_rejected_before_provider_preflight():
    plan = build_immutable_plan(
        complete_input(), suite_path=SUITE, source_hash=file_sha256(MANIFEST),
        constraint_hash=file_sha256(CONSTRAINTS), source_manifest_path=str(MANIFEST),
        constraint_map_path=str(CONSTRAINTS), created_at="2026-09-11T10:00:00+00:00",
    )
    require_dispatch_authorization(plan, allow_paid=True, source_manifest_path=MANIFEST, constraint_map_path=CONSTRAINTS)
    altered = dict(plan)
    altered["candidates"] = list(plan["candidates"])
    altered["candidates"][0] = {**altered["candidates"][0], "model": "changed-model"}
    with pytest.raises(PilotBlockedError, match="plan hash mismatch"):
        require_dispatch_authorization(altered, allow_paid=True, source_manifest_path=MANIFEST, constraint_map_path=CONSTRAINTS)
