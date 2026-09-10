import threading
from pathlib import Path

import pytest

from model_lab.benchmark import load_suite
from model_lab.errors import BudgetExceededError, IntegrityError
from model_lab.execution import ExecutionEngine
from model_lab.providers import FakeProvider, FakeVariant, OllamaProvider, ProviderConfigurationError
from model_lab.schemas import Budget, ModelConfig, Run
from model_lab.storage import SQLiteStore


ROOT = Path(__file__).parents[1]


def make_run(suite, *, run_id="run-test", budget=None):
    return Run(run_id, suite.suite_version, tuple(suite.case_ids), ModelConfig("fake", "synthetic-v1", parameters={"temperature": 0}), 7, budget or Budget(), "2026-01-01T00:00:00+00:00")


def test_sqlite_persists_run_attempt_and_rejects_immutable_duplicate(tmp_path):
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    store = SQLiteStore(tmp_path / "lab.sqlite")
    run = make_run(suite)
    result = ExecutionEngine(store, FakeProvider(FakeVariant.CORRECT)).execute(suite, run, case_ids=suite.case_ids[:2])
    assert result.status == "completed"
    assert len(store.list_attempts(run.run_id)) == 2
    with pytest.raises(IntegrityError):
        store.add_attempt(result.attempts[0])
    assert store.get_run(run.run_id).run_id == run.run_id


def test_fake_failure_retries_and_preserves_each_raw_attempt():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    store = SQLiteStore()
    run = make_run(suite, run_id="run-retry")
    result = ExecutionEngine(store, FakeProvider(fail_times=1), max_retries=1).execute(suite, run, case_ids=[suite.case_ids[0]])
    assert result.status == "completed"
    assert len(result.attempts) == 2
    assert result.attempts[0].status.value == "provider_failure"
    assert result.attempts[1].status.value == "success"


def test_cancellation_marks_partial_or_cancelled_without_dispatching_remaining_cases():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    store = SQLiteStore()
    run = make_run(suite, run_id="run-cancel")
    event = threading.Event()
    event.set()
    result = ExecutionEngine(store, FakeProvider()).execute(suite, run, case_ids=suite.case_ids[:3], cancel_event=event)
    assert result.status == "cancelled"
    assert result.attempts == ()


def test_budget_stops_after_request_limit():
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    store = SQLiteStore()
    run = make_run(suite, run_id="run-budget", budget=Budget(max_requests=1))
    result = ExecutionEngine(store, FakeProvider()).execute(suite, run, case_ids=suite.case_ids[:2])
    assert len(result.attempts) == 1
    assert result.status == "partial"


def test_live_adapter_fails_closed_without_secret():
    with pytest.raises(ProviderConfigurationError):
        OllamaProvider("local", env={}).generate(None)  # type: ignore[arg-type]
