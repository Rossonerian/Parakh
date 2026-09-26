import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import DataTable, RichLog  # noqa: E402

from model_lab.application import lab_actions  # noqa: E402
from model_lab.application.events import record_event  # noqa: E402
from model_lab.storage import SQLiteStore  # noqa: E402
from model_lab.tui.app import ParakhApp  # noqa: E402
from model_lab.tui.views import DashboardView  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "benchmarks/seed_cases.jsonl"


def _text(widget) -> str:
    return str(widget.render())


def _table_text(table: DataTable) -> str:
    return "\n".join(" ".join(str(cell) for cell in table.get_row_at(i)) for i in range(table.row_count))


async def _until(pilot, condition, timeout: float = 20.0) -> None:
    waited = 0.0
    while not condition():
        await pilot.pause(0.1)
        waited += 0.1
        if waited > timeout:
            raise AssertionError("condition not reached")


def run(coro):
    return asyncio.run(coro)


def test_starts_on_empty_workspace_without_creating_runs(tmp_path):
    async def scenario():
        app = ParakhApp(data_dir=tmp_path / "ws", suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(160, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None)
            latest = _text(app.query_one("#dash-latest"))
            assert "No runs yet" in latest
            assert "not created yet" in _text(app.query_one("#dash-workspace"))
            for key in "1234567890l":
                await pilot.press(key)
            await pilot.pause(0.2)
            assert app.query_one("#runs-table", DataTable).row_count == 0
            assert app.query_one("#cases-table", DataTable).row_count == 60
    run(scenario())


def test_missing_suite_is_reported_not_fatal(tmp_path):
    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=tmp_path / "missing.jsonl", poll_seconds=0.1)
        async with app.run_test(size=(160, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None)
            assert "N/A" in _text(app.query_one("#dash-workspace"))
            assert app.state.snapshot.health["offline_ready"] is False
    run(scenario())


def test_live_run_progress_completion_and_event_log(tmp_path):
    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(160, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None)
            app.start_action("fake run", lambda: lab_actions.run_fake(tmp_path, SUITE, max_cases=12, pacing_seconds=0.05), str)
            await _until(pilot, lambda: bool(app.state.snapshot.active) and app.state.snapshot.active[0].completed >= 1)
            active = app.state.snapshot.active[0]
            assert 1 <= active.completed < active.total == 12
            assert "Active execution" in app.query_one("#dash-active").border_title
            assert "running" in _text(app.query_one("#statusbar"))
            await _until(pilot, lambda: "fake run" not in app.busy and not app.state.snapshot.active and app.state.snapshot.runs[0].status == "completed")
            run_summary = app.state.snapshot.runs[0]
            assert run_summary.cases_attempted == 12 and run_summary.graded == 12
            await pilot.press("l")  # RichLog renders once its tab is laid out
            await _until(pilot, lambda: "run finished" in "\n".join(line.text for line in app.query_one("#event-log", RichLog).lines))
            runs_text = _table_text(app.query_one("#runs-table", DataTable))
            assert "SIMULATED" in runs_text and "12/12" in runs_text and "not measured" in runs_text
    run(scenario())


def test_failed_run_and_long_labels_render(tmp_path):
    long_model = "synthetic-" + "x" * 150
    lab_actions.run_fake(tmp_path, SUITE, model=long_model, variant="failure", max_cases=3, pacing_seconds=0)

    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(100, 40)) as pilot:
            await _until(pilot, lambda: app.state is not None and app.state.snapshot.runs)
            await pilot.press("5")
            await pilot.pause(0.2)
            text = _table_text(app.query_one("#runs-table", DataTable))
            assert "partial" in text and "3/3" in text
            assert "failed" in _text(app.query_one("#dash-latest")) or "0 passed" in _text(app.query_one("#dash-latest"))
            await pilot.press("9")
            await pilot.pause(0.2)
            assert app.query_one("#review-table", DataTable).row_count == 3
            app.query_one(DashboardView).show(app.state)  # rendering the long label must not raise
    run(scenario())


def test_secrets_never_reach_the_console(tmp_path, monkeypatch):
    secret = "sk-or-v1-thisisnotarealkey0987654321"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    store = SQLiteStore(tmp_path / "model_lab.sqlite3")
    record_event(store, "action_failed", f"provider rejected key {secret}", error=f"HTTP 401 for {secret}")
    store.close()

    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(160, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None and app.state.snapshot.events)
            await pilot.press("l")
            await pilot.pause(0.3)
            log = "\n".join(line.text for line in app.query_one("#event-log", RichLog).lines)
            assert "[REDACTED]" in log and secret not in log
            await pilot.press("4")
            await pilot.pause(0.2)
            models = _table_text(app.query_one("#models-table", DataTable))
            assert "value hidden" in models and secret not in models
    run(scenario())


def test_console_has_no_paid_dispatch_path(tmp_path, monkeypatch):
    import model_lab.pilot as pilot_module

    def forbidden(*_args, **_kwargs):
        raise AssertionError("paid dispatch attempted from the console")

    monkeypatch.setattr(pilot_module, "run_authorized_immutable_pilot", forbidden)
    monkeypatch.setattr(pilot_module, "_provider_for", forbidden)
    plan = tmp_path / "plan.json"
    plan.write_text('{"plan_hash": "abc123", "immutable": true, "candidates": [{"provider": "openrouter", "model": "m"}]}', encoding="utf-8")

    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=SUITE, plan_path=str(plan), poll_seconds=0.1)
        async with app.run_test(size=(160, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None and app.state.preflight is not None)
            result = _text(app.query_one("#pilot-result"))
            assert "disabled" in result and "blocked" in result
    run(scenario())
