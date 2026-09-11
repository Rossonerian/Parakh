import json
from pathlib import Path

import pytest

from model_lab.cli import main
from model_lab.pilot import (
    PilotBlockedError,
    build_pilot_plan,
    parse_candidate_spec,
    require_dispatch_authorization,
    validate_pilot_plan,
)


ROOT = Path(__file__).parents[1]


def test_pilot_plan_is_exactly_development_split_and_blocked_without_operator_input():
    plan = build_pilot_plan(ROOT / "benchmarks/seed_cases.jsonl")
    assert plan["case_count"] == 36
    assert len(plan["case_ids"]) == 36
    assert plan["candidate_models"] == []
    assert plan["ready_for_paid_dispatch"] is False
    assert "L1-04" not in plan["case_ids"]  # calibration
    assert "L1-05" not in plan["case_ids"]  # holdout
    assert "operator_candidate_models_required" in validate_pilot_plan(plan)
    with pytest.raises(PilotBlockedError):
        require_dispatch_authorization(plan, allow_paid=True)


def test_candidate_spec_and_frozen_operator_fields():
    candidate = parse_candidate_spec("openrouter:openai/gpt-4.1:2026-01-01")
    plan = build_pilot_plan(
        ROOT / "benchmarks/seed_cases.jsonl",
        candidates=[candidate],
        repeats=2,
        max_spend_minor=5000,
        currency="USD",
        pricing_snapshot={"source": "operator", "revision": "rate-v1"},
    )
    assert plan["candidate_models"][0]["model"] == "openai/gpt-4.1"
    assert plan["frozen_configuration"]["execution"]["repeats"] == 2
    assert plan["budget"]["max_spend_minor"] == 5000
    assert plan["routing_constraints"]["production_router_change"] is False


def test_cli_pilot_plan_and_show_are_safe(tmp_path: Path):
    plan_path = tmp_path / "pilot.json"
    assert main(["pilot", "plan", "--suite", str(ROOT / "benchmarks/seed_cases.jsonl"), "--out", str(plan_path)]) == 0
    assert main(["pilot", "show", str(plan_path)]) == 2
    assert main(["pilot", "run", "--plan", str(plan_path), "--allow-paid"]) == 2
    value = json.loads(plan_path.read_text(encoding="utf-8"))
    assert value["case_count"] == 36
    assert value["authorization"]["paid_dispatch_allowed"] is False

