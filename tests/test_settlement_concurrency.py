import threading
import sqlite3
import pytest
from pathlib import Path

from model_lab.storage import SQLiteStore, IntegrityError
from model_lab.schemas import Budget, utc_now
from model_lab.budget import BudgetLedger

@pytest.fixture
def run_db(tmp_path):
    store = SQLiteStore(tmp_path / "model_lab.sqlite3")
    store.connection.execute("INSERT INTO runs (run_id, suite_version, case_ids_json, model_config_json, seed, budget_json, started_at, status, environment_json, created_record_json) VALUES (?, '1', '[]', '{}', 1, '{}', '2023', 'new', '{}', '{}')", ("run-1",))
    return store, tmp_path / "model_lab.sqlite3"

def test_same_store_concurrent_settlements_2(run_db):
    store, _ = run_db
    budgets = BudgetLedger(store)
    budget = Budget(currency="USD", max_cost_minor=1000)
    reservation = budgets.reserve("run-1", "req-1", budget, estimated_cost_minor=10)
    
    results = []
    def worker():
        try:
            budgets.settle(reservation, actual_cost_minor=5)
            results.append("success")
        except Exception as e:
            results.append(type(e).__name__)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert "success" in results
    assert results.count("success") == 1
    assert results.count("NotFoundError") == 1

def test_same_store_concurrent_settlements_50(run_db):
    store, _ = run_db
    budgets = BudgetLedger(store)
    budget = Budget(currency="USD", max_cost_minor=1000)
    reservation = budgets.reserve("run-1", "req-2", budget, estimated_cost_minor=10)
    
    results = []
    def worker():
        try:
            budgets.settle(reservation, actual_cost_minor=5)
            results.append("success")
        except Exception as e:
            results.append(type(e).__name__)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert results.count("success") == 1
    assert results.count("NotFoundError") == 49
    # No ProgrammingError

def test_multiple_connections_concurrent_settlement(run_db):
    _, db_path = run_db
    
    setup_store = SQLiteStore(db_path)
    budgets_setup = BudgetLedger(setup_store)
    budget = Budget(currency="USD", max_cost_minor=1000)
    reservation = budgets_setup.reserve("run-1", "req-3", budget, estimated_cost_minor=10)
    
    results = []
    def worker():
        # new connection per worker
        store = SQLiteStore(db_path)
        b = BudgetLedger(store)
        try:
            b.settle(reservation, actual_cost_minor=5)
            results.append("success")
        except Exception as e:
            results.append(type(e).__name__)
        finally:
            store.close()

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    assert results.count("success") == 1
    assert results.count("NotFoundError") == 9

