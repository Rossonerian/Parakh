"""Validation tests for synthetic student benchmark suite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from model_lab.benchmark import load_suite, validate_suite

STUDENT_DIR = Path(__file__).parents[1] / "benchmarks_student"


def test_student_suite_structure_and_validation() -> None:
    cases_file = STUDENT_DIR / "cases.jsonl"
    assert cases_file.exists(), "cases.jsonl must exist"

    # Validate using the real suite validator
    suite = load_suite(cases_file)
    validation = validate_suite(suite)

    assert validation["cases"] >= 48, f"Expected >= 48 cases, got {validation['cases']}"
    assert validation["cases"] == 49

    # Category counts assertion
    categories: dict[str, int] = {}
    for case in suite.cases:
        cat = case.tags[0]
        categories[cat] = categories.get(cat, 0) + 1

    assert categories["code"] == 10
    assert categories["maths"] == 10
    assert categories["study"] == 10
    assert categories["hindi"] == 8
    assert categories["mixed"] == 8
    assert categories["summary"] == 3


def test_student_splits_and_no_leakage() -> None:
    suite = load_suite(STUDENT_DIR / "cases.jsonl")

    train_ids: set[str] = set()
    calib_ids: set[str] = set()
    holdout_ids: set[str] = set()

    train_prompts: set[str] = set()
    calib_prompts: set[str] = set()
    holdout_prompts: set[str] = set()

    summary_long_cases = 0

    for case in suite.cases:
        content = case.messages[0]["content"]
        if case.tags[0] == "summary" and len(content) >= 6000:
            summary_long_cases += 1

        if case.split == "train":
            train_ids.add(case.case_id)
            train_prompts.add(content)
        elif case.split == "calibration":
            calib_ids.add(case.case_id)
            calib_prompts.add(content)
        elif case.split == "holdout":
            holdout_ids.add(case.case_id)
            holdout_prompts.add(content)

    assert summary_long_cases == 1, f"Expected exactly one >=6k long-context summary case, got {summary_long_cases}"

    # Assert no overlap of IDs across splits
    assert not (train_ids & calib_ids), "ID overlap between train and calibration"
    assert not (train_ids & holdout_ids), "ID overlap between train and holdout"
    assert not (calib_ids & holdout_ids), "ID overlap between calibration and holdout"

    # Assert no overlap of prompt contents across splits
    assert not (train_prompts & calib_prompts), "Prompt overlap between train and calibration"
    assert not (train_prompts & holdout_prompts), "Prompt overlap between train and holdout"
    assert not (calib_prompts & holdout_prompts), "Prompt overlap between calibration and holdout"


def test_holdout_hash_matches_manifest() -> None:
    manifest_file = STUDENT_DIR / "manifest.json"
    holdout_file = STUDENT_DIR / "holdout.jsonl"
    sha_file = STUDENT_DIR / "holdout.sha256"

    assert manifest_file.exists()
    assert holdout_file.exists()
    assert sha_file.exists()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    actual_holdout_hash = hashlib.sha256(holdout_file.read_bytes()).hexdigest()

    assert manifest["holdout_sha256"] == actual_holdout_hash, "Manifest holdout hash mismatch"
    assert actual_holdout_hash in sha_file.read_text(encoding="utf-8"), "holdout.sha256 file mismatch"


def test_automated_checks_pass_on_reference_answers() -> None:
    ref_file = STUDENT_DIR / "reference_evaluations.json"
    assert ref_file.exists()
    references = json.loads(ref_file.read_text(encoding="utf-8"))
    assert len(references) == 49

    for case_id, ref in references.items():
        check_type = ref["check_type"]
        answer = ref["reference_answer"]

        if check_type == "python_exec":
            code = answer + "\n" + ref["check_code"]
            local_scope: dict[str, object] = {}
            exec(code, {}, local_scope)  # noqa: S102

        elif check_type == "exact_numeric":
            match = re.search(r"[-+]?\d*\.?\d+", answer)
            assert match is not None, f"No number found in {answer} for {case_id}"
            num = float(match.group())
            assert abs(num - float(ref["expected"])) < 1e-5, f"Numeric mismatch for {case_id}"

        elif check_type == "exact_string":
            assert ref["expected"].strip() in answer.strip(), f"String mismatch for {case_id}"

        elif check_type == "keywords":
            lower_ans = answer.lower()
            for kw in ref["keywords"]:
                assert kw.lower() in lower_ans, f"Keyword '{kw}' not in reference answer for {case_id}"

        elif check_type == "devanagari":
            # Verify Devanagari script presence
            has_devanagari = bool(re.search(r"[\u0900-\u097F]", answer))
            assert has_devanagari, f"No Devanagari characters in answer for {case_id}"
            for kw in ref.get("keywords", []):
                assert kw in answer, f"Hindi keyword '{kw}' not in answer for {case_id}"

        elif check_type == "mixed_script":
            lower_ans = answer.lower()
            for kw in ref.get("keywords", []):
                assert kw.lower() in lower_ans, f"Mixed keyword '{kw}' not in answer for {case_id}"
