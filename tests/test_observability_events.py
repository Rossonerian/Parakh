import json
import sqlite3
from pathlib import Path

import pytest

from model_lab.application import lab_actions
from model_lab.application.events import record_event, redact
from model_lab.application.observability import case_views, load_snapshot, summarize_cost
from model_lab.benchmark import load_suite
from model_lab.pipeline import run_offline_demo
from model_lab.schemas import Attempt, AttemptStatus, ModelConfig
from model_lab.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "benchmarks/seed_cases.jsonl"


def _events(data_dir: Path, run_id: str):
    store = SQLiteStore(data_dir / "model_lab.sqlite3")
    try:
        return store.list_events(run_id=run_id, limit=10_000)
    finally:
        store.close()


def test_engine_records_ordered_lifecycle_with_retries(tmp_path):
    result = lab_actions.run_fake(tmp_path, SUITE, variant="failure", max_cases=2, max_retries=1, pacing_seconds=0)
    types = [event.event_type for event in _events(tmp_path, result["run_id"])]
    per_case = ["case_started", "provider_request_started", "response_received", "retry_scheduled",
                "provider_request_started", "response_received", "case_failed"]
    assert types == ["run_started", *per_case, *per_case, "run_finished", "grading_started", "grading_finished"]
    events = _events(tmp_path, result["run_id"])
    assert events[1].message == "case 1/2 started" and events[8].message == "case 2/2 started"
    assert events[-3].status == "partial"
    assert all(event.duration_ms is not None for event in events if event.event_type == "response_received")


def test_events_are_append_only(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite3")
    record_event(store, "doctor", "ok")
    for statement in ("UPDATE run_events SET event_type = 'x'", "DELETE FROM run_events"):
        with pytest.raises(sqlite3.DatabaseError, match="immutable evidence"):
            store.connection.execute(statement)
    store.close()


def test_secrets_are_redacted_before_storage(tmp_path, monkeypatch):
    secret = "sk-or-v1-supersecretvalue1234567890"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    store = SQLiteStore(tmp_path / "db.sqlite3")
    record_event(store, "action_failed", f"call failed with key {secret}", error=f"401 Authorization: Bearer abcdef123456789 token={secret}")
    stored = store.connection.execute("SELECT record_json FROM run_events").fetchone()[0]
    store.close()
    assert secret not in stored and "abcdef123456789" not in stored
    assert "[REDACTED]" in stored
    assert redact("x" * 600).endswith("…") and len(redact("x" * 600)) == 500


def _attempt(index: int, cost: int | None, currency: str | None) -> Attempt:
    return Attempt(attempt_id=f"a{index}", run_id="r", logical_request_id=f"l{index}", case_id=f"c{index}",
                   model_config=ModelConfig(provider="fake", model="m"), prompt_hash="h", response_text="x",
                   status=AttemptStatus.SUCCESS, started_at="2026-01-01T00:00:00+00:00", cost_minor=cost, currency=currency)


def test_cost_is_never_summed_across_currencies_or_with_unknowns():
    assert summarize_cost([_attempt(1, 100, "USD"), _attempt(2, 50, "USD")]).total_minor == 150
    mixed = summarize_cost([_attempt(1, 100, "USD"), _attempt(2, 50, "INR")])
    assert mixed.total_minor is None and "mixed" in mixed.note
    partial = summarize_cost([_attempt(1, 100, "USD"), _attempt(2, None, None)])
    assert partial.total_minor is None and partial.unknown == 1
    assert summarize_cost([_attempt(1, None, None)]).note == "not measured"


def test_snapshot_of_missing_workspace_is_usable_and_creates_nothing(tmp_path):
    data_dir = tmp_path / "absent"
    snapshot = load_snapshot(data_dir, SUITE)
    assert not snapshot.db_exists and snapshot.runs == [] and snapshot.events == []
    assert snapshot.suite is not None and snapshot.suite.cases == 60
    assert not data_dir.exists()


def test_case_views_never_carry_oracle_data():
    suite = load_suite(SUITE)
    rendered = json.dumps([view.__dict__ for view in case_views(suite)], default=str)
    for case in suite.cases:
        reference = case.evaluation.reference_answer
        if isinstance(reference, (dict, list)) and reference:
            assert json.dumps(reference, sort_keys=True) not in rendered
        for rubric_item in case.evaluation.rubric or ():
            text = rubric_item if isinstance(rubric_item, str) else json.dumps(rubric_item, default=str)
            assert text not in rendered


def test_demos_accumulate_in_one_workspace_database(tmp_path):
    db = tmp_path / "model_lab.sqlite3"
    run_offline_demo(SUITE, tmp_path / "a", database=db, run_id_prefix="demo-a")
    run_offline_demo(SUITE, tmp_path / "b", database=db, run_id_prefix="demo-b")
    snapshot = load_snapshot(tmp_path, SUITE)
    assert [run.run_id for run in snapshot.runs] == ["demo-b-synthetic-incorrect", "demo-b-synthetic-good",
                                                      "demo-a-synthetic-incorrect", "demo-a-synthetic-good"]
    good = snapshot.runs[1]
    assert good.provenance == "SIMULATED" and good.status == "completed"
    assert good.cost.total_minor is None and good.latency_ms_mean is None  # fake provider reports neither


def test_pilot_preflight_never_dispatches(tmp_path, monkeypatch):
    import model_lab.pilot as pilot

    def forbidden(*_args, **_kwargs):
        raise AssertionError("live provider construction attempted")

    monkeypatch.setattr(pilot, "_provider_for", forbidden)
    monkeypatch.setattr(pilot, "run_authorized_immutable_pilot", forbidden)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"plan_hash": "abc123", "candidates": [{"provider": "openrouter", "model": "x"}]}), encoding="utf-8")
    result = lab_actions.pilot_preflight(plan)
    assert result["paid_dispatch_from_tui"] is False
    assert "live pilot blocked" in result["gate"] and "explicit_allow_paid_acknowledgement_required" in result["gate"]
    assert result["plan_blockers"]
