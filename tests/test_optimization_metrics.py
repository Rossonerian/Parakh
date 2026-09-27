"""Cost and reward efficiency must not silently mix currencies or unknown denominators."""

from model_lab.optimization.metrics import compounding_metrics
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore


def test_compounding_efficiency_requires_complete_comparable_cost_and_latency(tmp_path):
    store = SQLiteStore(tmp_path / "metrics.sqlite3")
    try:
        evidence = EvidenceStore(store)

        def add(run_id, *, cost, currency, completed, latency):
            evidence.append("trajectories", run_id, {"run_id": run_id, "final_outcome": {
                "final_cost": cost, "currency": currency, "completed": completed, "final_latency_ms": latency}})
            evidence.append("rewards", run_id, {"subject_type": "telemetry_run", "subject_id": run_id, "scalar": 0.5})

        add("success", cost=2.0, currency="USD", completed=True, latency=1000)
        add("failed", cost=1.0, currency="USD", completed=False, latency=2000)
        comparable = compounding_metrics(evidence)
        assert comparable["cost_per_successful_run_usd"] == 3.0  # failures still cost money
        assert comparable["reward_per_dollar"] == 1.0 / 3.0
        assert comparable["reward_per_second"] == 1.0 / 3.0

        add("other-currency", cost=2.0, currency="EUR", completed=True, latency=None)
        mixed = compounding_metrics(evidence)
        assert mixed["cost_per_successful_run_usd"] is None
        assert mixed["reward_per_dollar"] is None
        assert mixed["reward_per_second"] is None
        assert mixed["mean_reward"] == 0.5
    finally:
        store.close()


def test_data_efficiency_uses_candidate_count_not_accepted_run_count(tmp_path):
    store = SQLiteStore(tmp_path / "efficiency.sqlite3")
    try:
        evidence = EvidenceStore(store)
        for i in range(6):
            evidence.append("telemetry_records", f"run-{i}", {"run_id": f"run-{i}", "status": "accepted"})
        empty = compounding_metrics(evidence)["data_efficiency_ratio"]
        assert empty["value"] is None
        for candidate_id in ("novel-1", "novel-2"):
            evidence.append("evaluation_candidates", candidate_id, {"candidate_id": candidate_id, "duplicate_of": None})
            evidence.transition("evaluation_candidate", candidate_id, "NEW", actor="importer", reason="import")
            evidence.transition("evaluation_candidate", candidate_id, "VALIDATED", actor="importer", reason="validated")
        evidence.transition("evaluation_candidate", "novel-1", "APPROVED", actor="reviewer", reason="novel")
        ratio = compounding_metrics(evidence)["data_efficiency_ratio"]
        assert ratio["value"] == 0.5
        assert ratio["approved_candidates"] == 1
        assert ratio["imported_candidates"] == 2
    finally:
        store.close()
