import json
from pathlib import Path

import pytest

from model_lab.benchmark import load_suite, validate_suite
from model_lab.errors import ValidationError
from model_lab.isolation import assert_candidate_safe, candidate_input


ROOT = Path(__file__).parents[1]


def test_seed_suite_validates_with_expected_shape():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    summary = validate_suite(suite)
    assert summary["cases"] == 60
    assert summary["domains"] == 15
    assert summary["complexity"] == {"1": 15, "2": 15, "3": 15, "4": 15}
    assert summary["splits"] == {"calibration": 12, "holdout": 12, "train": 36}


def test_candidate_projection_has_no_oracles_or_split_metadata():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    projected = candidate_input(case)
    payload = projected.to_dict()
    assert_candidate_safe(payload)
    serialized = json.dumps(payload, sort_keys=True)
    for secret in ("reference_answer", "rubric", "critical_failures", "holdout", case.family_id):
        assert secret not in serialized


def test_candidate_projection_is_immutable():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    projected = candidate_input(case)
    with pytest.raises(TypeError):
        projected.limits["max_tool_calls"] = 99
    with pytest.raises(AttributeError):
        _ = projected.evaluation


def test_duplicate_and_invalid_records_are_rejected(tmp_path):
    source = ROOT / "benchmarks/seed_cases.jsonl"
    lines = source.read_text(encoding="utf-8").splitlines()
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate case IDs"):
        load_suite(duplicate)

    invalid = tmp_path / "invalid.jsonl"
    data = json.loads(lines[0])
    data["complexity_level"] = 5
    invalid.write_text(json.dumps(data) + "\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="complexity_level"):
        load_suite(invalid)

