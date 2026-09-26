"""Console state assembled off the UI thread from the observability read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from model_lab.analysis import ComparisonResult
from model_lab.application.observability import (
    CaseView, RunResults, RunSummary, Snapshot, SuiteSummary, case_views, load_snapshot, open_store, run_results,
    safe_environment_checks, summarize_loaded_suite,
)
from model_lab.benchmark import load_suite
from model_lab.errors import ModelLabError
from model_lab.schemas import RunEvent, Suite


@dataclass
class ConsoleState:
    snapshot: Snapshot
    selected_run: RunSummary | None = None
    results: RunResults | None = None
    run_events: list[RunEvent] = field(default_factory=list)
    cases: list[CaseView] = field(default_factory=list)
    comparison: ComparisonResult | None = None
    comparison_runs: tuple[str, str] | None = None
    routing: list[dict[str, Any]] = field(default_factory=list)
    preflight: dict[str, Any] | None = None
    suite_error: str | None = None


class SuiteCache:
    """Parse the suite (and run the doctor checks) once per file modification.

    Also holds per-run summaries so polling only re-summarizes runs that changed.
    """

    def __init__(self) -> None:
        self._key: tuple[str, float] | None = None
        self._suite: Suite | None = None
        self.error: str | None = None
        self.summary: SuiteSummary | None = None
        self.health: dict[str, Any] | None = None
        self.run_summaries: dict[str, Any] = {}

    def invalidate(self) -> None:
        self._key = None

    def get(self, path: str | Path) -> Suite | None:
        source = Path(path)
        try:
            key = (str(source.resolve()), source.stat().st_mtime)
        except OSError as exc:
            self._suite, self.error = None, f"suite not readable: {exc}"
            return None
        if key != self._key:
            self._key = key
            try:
                self._suite, self.error = load_suite(source), None
                self.summary = summarize_loaded_suite(self._suite, source)
            except (ModelLabError, ValueError) as exc:
                self._suite, self.error = None, str(exc)
                self.summary = SuiteSummary(str(source), None, None, 0, 0, {}, {}, {}, error=str(exc))
            self.health = safe_environment_checks(source)
        return self._suite


def build_state(data_dir: str | Path, suite_path: str | Path, suites: SuiteCache, *, selected_run_id: str | None) -> ConsoleState:
    suite = suites.get(suite_path)
    snapshot = load_snapshot(data_dir, suite_path, suite=suites.summary, health=suites.health, summary_cache=suites.run_summaries)
    runs = {run.run_id: run for run in snapshot.runs}
    if selected_run_id not in runs:
        selected_run_id = snapshot.active[0].run_id if snapshot.active else (snapshot.runs[0].run_id if snapshot.runs else None)
    state = ConsoleState(snapshot=snapshot, suite_error=suites.error)
    store = open_store(data_dir) if snapshot.db_exists else None
    try:
        attempts_by_case: dict = {}
        grades_by_attempt: dict = {}
        if store is not None and selected_run_id is not None:
            state.selected_run = runs[selected_run_id]
            state.results = run_results(store, suite, selected_run_id)
            state.run_events = store.list_events(run_id=selected_run_id, limit=150)
            for attempt in store.list_attempts(selected_run_id):
                attempts_by_case[attempt.case_id] = attempt
            grades_by_attempt = {g.attempt_id: g for g in store.list_grades(selected_run_id)}
        if suite is not None:
            state.cases = case_views(suite, attempts_by_case, grades_by_attempt)
    finally:
        if store is not None:
            store.close()
    return state
