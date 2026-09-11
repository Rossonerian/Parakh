import json
from pathlib import Path

import pytest

from model_lab.benchmark import load_suite
from model_lab.budget import BudgetLedger
from model_lab.errors import BudgetExceededError
from model_lab.ingestion import ingest_file, ingest_records
from model_lab.schemas import Budget, ModelConfig, Run
from model_lab.storage import SQLiteStore


ROOT = Path(__file__).parents[1]


def setup_run(store):
    suite = load_suite(ROOT / "benchmarks/seed_cases.jsonl")
    run = Run("run-import", suite.suite_version, tuple(suite.case_ids[:2]), ModelConfig("fake", "synthetic-v1"), None, Budget(max_requests=2), "2026-01-01T00:00:00+00:00")
    store.create_run(run)
    return suite, run


def record(suite, attempt_id="import-1"):
    return {"attempt_id": attempt_id, "case_id": suite.case_ids[0], "prompt_hash": suite.cases[0].prompt_hash, "response_text": "safe output", "provider": "fake", "model": "synthetic-v1", "status": "success"}


def test_import_duplicate_and_mismatch_are_quarantined(tmp_path):
    store = SQLiteStore(tmp_path / "import.sqlite")
    suite, run = setup_run(store)
    first = record(suite)
    result = ingest_records(store, run.run_id, [first, first, {**first, "attempt_id": "import-2", "case_id": "not-in-run"}], source_label="fixture")
    assert result.imported == 1
    assert result.duplicates == 1
    assert result.quarantined == 2
    assert len(store.quarantined()) == 2


def test_jsonl_import_preserves_unknown_metrics_as_null(tmp_path):
    store = SQLiteStore()
    suite, run = setup_run(store)
    path = tmp_path / "answers.jsonl"
    path.write_text(json.dumps(record(suite)) + "\n", encoding="utf-8")
    result = ingest_file(store, run.run_id, path, fmt="jsonl")
    assert result.imported == 1
    attempt = store.get_attempt("import-1")
    assert attempt.cost_minor is None
    assert attempt.input_tokens is None
    assert attempt.first_token_latency_ms is None


def test_budget_requires_known_cost_when_finite_cost_cap():
    store = SQLiteStore()
    suite, run = setup_run(store)
    ledger = BudgetLedger(store)
    with pytest.raises(BudgetExceededError):
        ledger.reserve(run.run_id, "request-cost", Budget(max_cost_minor=10, currency="USD"))
    reservation = ledger.reserve(run.run_id, "request-known", Budget(max_cost_minor=10, currency="USD"), estimated_cost_minor=4)
    ledger.settle(reservation, actual_cost_minor=None)
    assert store.connection.execute("SELECT state, actual_cost_minor FROM budget_reservations WHERE reservation_id = ?", (reservation.reservation_id,)).fetchone()[0] == "unknown"


def test_unknown_provider_cost_keeps_its_conservative_reservation():
    store = SQLiteStore()
    _, run = setup_run(store)
    ledger = BudgetLedger(store)
    reservation = ledger.reserve(run.run_id, "request-one", Budget(max_cost_minor=10, currency="USD"), estimated_cost_minor=6)
    ledger.settle(reservation, actual_cost_minor=None)
    with pytest.raises(BudgetExceededError, match="cost budget exhausted"):
        ledger.reserve(run.run_id, "request-two", Budget(max_cost_minor=10, currency="USD"), estimated_cost_minor=5)


def test_csv_import(tmp_path):
    store = SQLiteStore()
    suite, run = setup_run(store)
    path = tmp_path / "answers.csv"
    path.write_text("attempt_id,case_id,prompt_hash,response_text,provider,model\nimport-csv,%s,%s,hello,fake,synthetic-v1\n" % (suite.case_ids[0], suite.cases[0].prompt_hash), encoding="utf-8")
    assert ingest_file(store, run.run_id, path, fmt="csv").imported == 1
