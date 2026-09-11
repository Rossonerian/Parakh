from copy import deepcopy
import json
from pathlib import Path

import pytest

from model_lab.operator_input import (
    OperatorInputError,
    build_immutable_plan,
    load_operator_input,
    parse_candidate_identifier,
    validate_operator_input,
    write_immutable_plan,
)


ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / "docs/live_pilots/operator-input.template.yaml"
SUITE = ROOT / "benchmarks/seed_cases.jsonl"


def complete_input() -> dict:
    value = load_operator_input(TEMPLATE)
    candidates = [
        ("ollama:local-a:rev-a", "Ollama A"),
        ("openrouter:vendor/model-b:rev-b", "Remote B"),
        ("openrouter:vendor/model-c:rev-c", "Remote C"),
    ]
    value["candidates"] = []
    value["pricing_snapshot"]["as_of"] = "2026-09-11"
    value["pricing_snapshot"]["currency"] = "USD"
    value["pricing_snapshot"]["source"] = "operator-rate-card-2026-09-11"
    value["pricing_snapshot"]["rates"] = {}
    value["budget"]["currency"] = "USD"
    value["budget"]["total_max_spend"] = 10
    value["budget"]["per_model_max_spend"] = {}
    for identifier, label in candidates:
        provider, model, *revision = identifier.split(":")
        value["candidates"].append({"identifier": identifier, "provider": provider, "model": model, "display_label": label, "revision": revision[0] if revision else ""})
        value["pricing_snapshot"]["rates"][identifier] = {"input_per_million": 0.1, "output_per_million": 0.2, "cache_per_million": 0, "reasoning_per_million": 0, "tool_per_call": 0}
        value["budget"]["per_model_max_spend"][identifier] = 5
    value["execution"].update({"max_input_tokens": 1000, "max_output_tokens": 500, "timeout_seconds": 30, "retry_limit": 1, "concurrency": 1, "repeats": 2, "temperature": 0, "seed": 17})
    value["authorization"] = {"operator_identity": "operator@example.test", "authorized_at": "2026-09-11T10:00:00Z", "approved": True, "maximum_spend_authorized": 10}
    return value


def test_template_is_parseable_but_fail_closed():
    value = load_operator_input(TEMPLATE)
    assert value["execution"]["repeats"] == 2
    with pytest.raises(OperatorInputError, match="candidate.identifier"):
        validate_operator_input(value, suite_path=SUITE)


def test_valid_input_is_train_only_and_has_conservative_bounds():
    plan = build_immutable_plan(complete_input(), suite_path=SUITE, created_at="2026-09-11T10:01:00+00:00")
    assert len(plan["case_ids"]) == 36
    assert plan["bounds"]["base_calls"] == 216
    assert plan["bounds"]["maximum_calls"] == 432
    assert plan["bounds"]["total_bound_minor"] <= 1000
    assert plan["immutable"] is True
    assert len(plan["plan_hash"]) == 64


@pytest.mark.parametrize("mutator, message", [
    (lambda x: x["candidates"].append(deepcopy(x["candidates"][0])), "unique"),
    (lambda x: x["budget"].update({"currency": "EUR"}), "currencies"),
    (lambda x: x["execution"].update({"max_output_tokens": 0}), "positive"),
    (lambda x: x["case_selection"].update({"split": "holdout"}), "train split"),
    (lambda x: x["authorization"].update({"approved": False}), "authorization"),
])
def test_invalid_operator_inputs_are_rejected(mutator, message):
    value = complete_input()
    mutator(value)
    with pytest.raises(OperatorInputError, match=message):
        validate_operator_input(value, suite_path=SUITE)


def test_duplicate_identifier_and_non_train_case_are_rejected():
    value = complete_input()
    value["candidates"][1]["identifier"] = value["candidates"][0]["identifier"]
    with pytest.raises(OperatorInputError, match="match identifier"):
        validate_operator_input(value, suite_path=SUITE)
    value = complete_input()
    value["case_selection"]["case_ids"] = ["L1-04"]
    with pytest.raises(OperatorInputError, match="calibration/holdout"):
        validate_operator_input(value, suite_path=SUITE)


def test_identifier_validation_and_immutable_write(tmp_path: Path):
    assert parse_candidate_identifier("ollama:model:rev") == ("ollama:model:rev", "ollama", "model", "rev")
    with pytest.raises(OperatorInputError, match="unsupported provider"):
        parse_candidate_identifier("unknown:model")
    plan = build_immutable_plan(complete_input(), suite_path=SUITE, created_at="2026-09-11T10:01:00+00:00")
    path = tmp_path / "plan.json"
    write_immutable_plan(plan, path)
    write_immutable_plan(plan, path)
    altered = dict(plan)
    altered["case_ids"] = list(plan["case_ids"][:-1])
    with pytest.raises(OperatorInputError, match="different content"):
        write_immutable_plan(altered, path)
    assert json.loads(path.read_text())["plan_hash"] == plan["plan_hash"]
