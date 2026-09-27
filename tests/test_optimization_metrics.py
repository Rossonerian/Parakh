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
