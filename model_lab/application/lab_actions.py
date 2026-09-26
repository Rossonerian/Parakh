"""Operator actions over a workspace directory (offline only).

Each action opens its own store connection, so it can run on a background
thread while a reader polls the same SQLite file. None of these functions can
reach a paid/live provider: runs use ``FakeProvider`` and the pilot preflight
calls the existing authorization gate with ``allow_paid=False``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from model_lab.analysis import ComparisonResult, compare_grades
from model_lab.application.events import record_event
from model_lab.application.execution import ExecutionEngine
from model_lab.application.observability import DB_NAME, environment_checks, provenance_label
from model_lab.benchmark import load_suite, validate_suite
from model_lab.errors import PilotBlockedError, ValidationError
from model_lab.ingestion import ingest_file
from model_lab.pilot import dispatch_preview, require_dispatch_authorization, validate_pilot_plan
from model_lab.pipeline import grade_run, run_offline_demo
from model_lab.providers.fake import FakeProvider, FakeVariant
from model_lab.routing import draft_recommendations
from model_lab.schemas import Budget, ModelConfig, Run, utc_now
from model_lab.storage import SQLiteStore

DEFAULT_PACING_SECONDS = 0.03


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]


def _store(data_dir: str | Path) -> SQLiteStore:
    return SQLiteStore(Path(data_dir) / DB_NAME)


def run_demo(data_dir: str | Path, suite_path: str | Path, *, pacing_seconds: float = DEFAULT_PACING_SECONDS, seed: int = 7,
             cancel_event: threading.Event | None = None) -> dict[str, Any]:
    """Two SIMULATED runs (oracle-fed "good" and deliberately wrong) + grading, reports, comparison, draft routing."""
    stamp = _stamp()
    return run_offline_demo(suite_path, Path(data_dir) / "demos" / stamp, seed=seed, database=Path(data_dir) / DB_NAME,
                            run_id_prefix=f"demo-{stamp}", provider_delay_seconds=pacing_seconds, cancel_event=cancel_event)


def run_fake(data_dir: str | Path, suite_path: str | Path, *, model: str = "synthetic-v1", variant: str = FakeVariant.CORRECT.value,
             max_cases: int | None = None, fail_times: int = 0, max_retries: int = 0, pacing_seconds: float = DEFAULT_PACING_SECONDS,
             seed: int = 7, cancel_event: threading.Event | None = None) -> dict[str, Any]:
    """One fake-provider run followed by deterministic grading."""
    suite = load_suite(suite_path)
    case_ids = suite.case_ids[:max_cases] if max_cases else suite.case_ids
    run = Run(run_id=f"tui-{_stamp()}", suite_version=suite.suite_version, case_ids=case_ids,
              model_config=ModelConfig(provider="fake", model=model, parameters={"temperature": 0, "synthetic": True, "variant": variant}),
              seed=seed, budget=Budget(max_cases=len(case_ids), max_requests=len(case_ids) * (max_retries + 1)), started_at=utc_now(),
              environment={"mode": "offline_synthetic", "suite_hash": suite.source_hash or "unknown", "pacing_delay_seconds": pacing_seconds},
              prompt_hashes={case_id: suite.get(case_id).prompt_hash for case_id in case_ids})
    store = _store(data_dir)
    try:
        provider = FakeProvider(variant=variant, model=model, fail_times=fail_times, delay_seconds=pacing_seconds)
        result = ExecutionEngine(store, provider, max_retries=max_retries).execute(suite, run, cancel_event=cancel_event)
        grades = grade_run(suite, store, list(result.attempts))
        return {"run_id": result.run_id, "status": result.status, "attempts": len(result.attempts), "failures": result.failures, "grades": len(grades)}
    finally:
        store.close()


def grade_ungraded(data_dir: str | Path, suite_path: str | Path, run_id: str) -> int:
    """Grade attempts that have no grade yet; returns how many were graded."""
    suite = load_suite(suite_path)
    store = _store(data_dir)
    try:
        graded = {g.attempt_id for g in store.list_grades(run_id)}
        missing = [a for a in store.list_attempts(run_id) if a.attempt_id not in graded and a.case_id in suite.case_ids]
        if not missing:
            record_event(store, "grading_skipped", "no ungraded attempts", run_id=run_id)
            return 0
        return len(grade_run(suite, store, missing))
    finally:
        store.close()


def validate(data_dir: str | Path, suite_path: str | Path) -> dict[str, Any]:
    result = validate_suite(load_suite(suite_path))
    store = _store(data_dir)
    try:
        record_event(store, "suite_validated", f"suite {result['suite_version']} valid: {result['cases']} cases, {result['families']} families",
                     status="valid", artifact=str(suite_path))
    finally:
        store.close()
    return result


def doctor(data_dir: str | Path, suite_path: str | Path) -> dict[str, Any]:
    checks = environment_checks(suite_path)
    store = _store(data_dir)
    try:
        failing = [k for k, v in checks.items() if v is False]
        record_event(store, "doctor", "offline ready" if checks.get("offline_ready") else f"not ready: {', '.join(failing) or 'benchmark case count'}",
                     status="ok" if checks.get("offline_ready") else "failed")
    finally:
        store.close()
    return checks


def import_results(data_dir: str | Path, run_id: str, path: str | Path, *, fmt: str | None = None) -> dict[str, int]:
    """Ingest external attempts into an existing run (quarantines invalid records)."""
    store = _store(data_dir)
    try:
        result = ingest_file(store, run_id, path, fmt=fmt, source_label="tui-import")
        record_event(store, "import_finished", f"imported {result.imported}, quarantined {result.quarantined}, duplicates {result.duplicates}",
                     run_id=run_id, status="imported", artifact=str(path))
        return {"imported": result.imported, "quarantined": result.quarantined, "duplicates": result.duplicates}
    finally:
        store.close()


def compare_runs(data_dir: str | Path, suite_path: str | Path, left_run: str, right_run: str) -> tuple[ComparisonResult, list[dict[str, Any]]]:
    """Matched-case comparison plus DRAFT routing evidence (never an activation)."""
    if left_run == right_run:
        raise ValidationError("choose two different runs")
    suite = load_suite(suite_path)
    store = _store(data_dir)
    try:
        left, right = store.get_run(left_run), store.get_run(right_run)
        comparison = compare_grades(store.list_grades(left_run), store.list_grades(right_run), cases=suite.cases,
                                    left_label=f"{left.model_config.model} ({left_run})", right_label=f"{right.model_config.model} ({right_run})")
        synthetic = "SIMULATED" in {provenance_label(left), provenance_label(right)}
        routing = draft_recommendations(comparison, cases=suite.cases, synthetic=synthetic)
        record_event(store, "comparison_computed", f"compared {left_run} vs {right_run}: {comparison.matched_cases} matched cases", status="draft")
        return comparison, routing
    finally:
        store.close()


def pilot_preflight(plan_path: str | Path) -> dict[str, Any]:
    """Show what a live pilot would dispatch and why it is blocked. Never dispatches."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValidationError("plan must be a JSON object")
    blockers = validate_pilot_plan(plan)
    try:
        require_dispatch_authorization(plan, allow_paid=False)
        gate = "unexpectedly open"
    except PilotBlockedError as exc:
        gate = str(exc)
    return {"preview": dispatch_preview(plan), "plan_blockers": blockers, "gate": gate,
            "paid_dispatch_from_tui": False,
            "how_to_dispatch": "model-lab pilot run --plan <immutable plan> --source-manifest <path> --constraint-map <path> --allow-paid"}
