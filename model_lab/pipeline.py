"""Boss-owned orchestration for the complete offline ModelLab workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .analysis import ComparisonResult, compare_grades
from .benchmark import load_suite
from .execution import ExecutionEngine
from .grading import grade_attempt
from .promptfoo import export_promptfoo_manifest, import_promptfoo_fixture
from .providers.fake import FakeProvider, FakeVariant
from .reporting import write_report_bundle
from .routing import draft_recommendations
from .schemas import Budget, ModelConfig, Run, canonical_record, utc_now
from .storage import SQLiteStore


def _candidate_output(case: Any, *, incorrect: bool = False) -> str:
    if incorrect:
        return "synthetic incorrect answer"
    reference = case.evaluation.reference_answer
    if isinstance(reference, str):
        return reference
    return json.dumps(reference, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _run_for_suite(suite: Any, *, run_id: str, model: str, seed: int, budget: Budget) -> Run:
    return Run(
        run_id=run_id,
        suite_version=suite.suite_version,
        case_ids=suite.case_ids,
        model_config=ModelConfig(provider="fake", model=model, parameters={"temperature": 0, "synthetic": True}),
        seed=seed,
        budget=budget,
        started_at=utc_now(),
        environment={"mode": "offline_synthetic", "suite_hash": suite.source_hash or "unknown"},
    )


def _rows(suite: Any, attempts: list[Any], grades: list[Any]) -> list[dict[str, Any]]:
    cases = {case.case_id: case for case in suite.cases}
    grade_by_attempt = {grade.attempt_id: grade for grade in grades}
    output: list[dict[str, Any]] = []
    for attempt in attempts:
        case = cases[attempt.case_id]
        grade = grade_by_attempt.get(attempt.attempt_id)
        output.append({
            "attempt_id": attempt.attempt_id,
            "case_id": attempt.case_id,
            "provider": attempt.model_config.provider,
            "model": attempt.model_config.model,
            "domain": case.domain,
            "workflow": case.family_id,
            "complexity_level": case.complexity_level,
            "split": case.split,
            "passed": grade.passed if grade else None,
            "score": grade.score if grade else None,
            "latency_ms": attempt.completion_latency_ms,
            "cost_minor": attempt.cost_minor,
            "response_text": attempt.response_text,
            "status": attempt.status.value,
            "prompt_hash": attempt.prompt_hash,
            "synthetic": True,
        })
    return output


def _digest(rows: list[dict[str, Any]]) -> str:
    stable = [{key: row.get(key) for key in ("case_id", "model", "status", "response_text", "score", "passed", "prompt_hash")} for row in rows]
    return hashlib.sha256(canonical_record(stable).encode("utf-8")).hexdigest()


def _execute_model(suite: Any, store: SQLiteStore, *, run_id: str, model: str, seed: int, incorrect: bool) -> tuple[Run, list[Any], list[Any], list[dict[str, Any]]]:
    outputs = {case.case_id: _candidate_output(case, incorrect=incorrect) for case in suite.cases}
    provider = FakeProvider(variant=FakeVariant.CORRECT, outputs=outputs, model=model)
    run = _run_for_suite(suite, run_id=run_id, model=model, seed=seed, budget=Budget(max_cases=len(suite.cases), max_requests=len(suite.cases)))
    result = ExecutionEngine(store, provider).execute(suite, run)
    grades = [grade_attempt(suite.get(attempt.case_id), attempt) for attempt in result.attempts]
    for grade in grades:
        store.add_grade(grade)
    rows = _rows(suite, list(result.attempts), grades)
    return run, list(result.attempts), grades, rows


def run_offline_demo(suite_path: str | Path, output_dir: str | Path, *, seed: int = 7) -> dict[str, Any]:
    """Run two explicitly synthetic 60-case models through every local layer."""
    suite = load_suite(suite_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(destination / "model_lab.sqlite3")
    try:
        good_run, good_attempts, good_grades, good_rows = _execute_model(suite, store, run_id="run-synthetic-good", model="synthetic-good", seed=seed, incorrect=False)
        bad_run, bad_attempts, bad_grades, bad_rows = _execute_model(suite, store, run_id="run-synthetic-incorrect", model="synthetic-incorrect", seed=seed, incorrect=True)
        comparison = compare_grades(good_grades, bad_grades, cases=suite.cases)
        routing = draft_recommendations(comparison, cases=suite.cases, eligibility={"synthetic-good": True, "synthetic-incorrect": True}, synthetic=True)
        good_report = write_report_bundle(good_rows, destination / "reports" / "synthetic-good", metadata={"run_id": good_run.run_id, "suite_version": suite.suite_version, "synthetic": True, "suite_hash": suite.source_hash})
        bad_report = write_report_bundle(bad_rows, destination / "reports" / "synthetic-incorrect", metadata={"run_id": bad_run.run_id, "suite_version": suite.suite_version, "synthetic": True, "suite_hash": suite.source_hash})
        manifest = export_promptfoo_manifest([case.candidate_payload() for case in suite.cases], run_id=good_run.run_id, provider="fake", model="synthetic-good")
        (destination / "promptfoo-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        promptfoo_fixture = {
            "artifact_type": "model_lab.promptfoo_result",
            "artifact_version": 1,
            "manifest_hash": manifest["manifest_hash"],
            "results": [{"case_id": attempt.case_id, "prompt_hash": attempt.prompt_hash, "output": attempt.response_text, "status": attempt.status.value} for attempt in good_attempts],
        }
        promptfoo_result = import_promptfoo_fixture(promptfoo_fixture, manifest)
        if not promptfoo_result.accepted:
            raise RuntimeError(f"offline Promptfoo fixture unexpectedly rejected: {promptfoo_result.errors}")
        (destination / "promptfoo-results.json").write_text(json.dumps(promptfoo_fixture, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        tampered = {**promptfoo_fixture, "results": [{**promptfoo_fixture["results"][0], "prompt_hash": "tampered"}] + promptfoo_fixture["results"][1:]}
        tampered_result = import_promptfoo_fixture(tampered, manifest, quarantine_dir=destination / "quarantine")
        comparison_dict = comparison.to_dict()
        (destination / "comparison.json").write_text(json.dumps(comparison_dict, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        (destination / "routing-evidence.json").write_text(json.dumps(routing, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        summary = {
            "synthetic": True,
            "suite_version": suite.suite_version,
            "suite_hash": suite.source_hash,
            "cases": len(suite.cases),
            "runs": {"synthetic-good": {"run_id": good_run.run_id, "status": store.get_run(good_run.run_id).status, "attempts": len(good_attempts), "grades": len(good_grades), "digest": _digest(good_rows)}, "synthetic-incorrect": {"run_id": bad_run.run_id, "status": store.get_run(bad_run.run_id).status, "attempts": len(bad_attempts), "grades": len(bad_grades), "digest": _digest(bad_rows)}},
            "comparison": comparison_dict,
            "routing_recommendations": routing,
            "promptfoo": {"accepted_fixture": promptfoo_result.accepted, "tampered_fixture_accepted": tampered_result.accepted, "tampered_errors": list(tampered_result.errors), "quarantine_path": str(tampered_result.quarantine_path) if tampered_result.quarantine_path else None},
            "reports": {"synthetic-good": {key: str(value) for key, value in good_report.items()}, "synthetic-incorrect": {key: str(value) for key, value in bad_report.items()}},
            "provenance": {"source": "offline_fake_provider", "provider": "fake", "model_quality_claim": False},
        }
        (destination / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return summary
    finally:
        store.close()
