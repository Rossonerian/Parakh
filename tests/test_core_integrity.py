from dataclasses import replace
from pathlib import Path

import pytest

from model_lab.benchmark import load_suite
from model_lab.errors import ValidationError
from model_lab.schemas import Budget, Limits, ModelConfig, Suite

ROOT = Path(__file__).parents[1]


def test_nested_records_are_detached_immutable_and_family_splits_are_enforced():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    case = suite.cases[0]
    with pytest.raises(TypeError):
        case.messages[0]["content"] = "tampered"
    params = {"nested": {"value": [1]}}
    model = ModelConfig("fake", "model", parameters=params)
    params["nested"]["value"].append(2)
    assert model.parameters["nested"]["value"] == (1,)
    leaked = replace(case, case_id="new-case", split="holdout")
    with pytest.raises(ValidationError, match="family"):
        Suite(suite.suite_version, (case, leaked))
    with pytest.raises(ValidationError):
        replace(case, messages=({"role": "user", "content": "safe", "evaluation": "secret"},))


@pytest.mark.parametrize("factory", [lambda: Budget(max_cost_minor=True, currency="USD"),
                                     lambda: Budget(max_runtime_seconds=float("nan")),
                                     lambda: Limits(True, 0),
                                     lambda: ModelConfig("fake", "model", parameters={"temperature": float("inf")})])
def test_nonfinite_or_boolean_numeric_contracts_rejected(factory):
    with pytest.raises(ValidationError):
        factory()
