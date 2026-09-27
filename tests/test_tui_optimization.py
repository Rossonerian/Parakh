"""Operator review screens for telemetry candidates, preference pairs and policy candidates."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, DataTable, Input, Select

from model_lab.application.observability import DB_NAME
from model_lab.preferences.extractor import extract_pairs
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.importer import import_batch
from model_lab.telemetry.schema import parse_batch
from model_lab.telemetry.synthetic import generate_batch
from model_lab.tui.app import ParakhApp

SUITE = Path(__file__).resolve().parents[1] / "benchmarks/seed_cases.jsonl"


async def _until(pilot, condition, timeout: float = 20.0) -> None:
    waited = 0.0
    while not condition():
        await pilot.pause(0.1)
        waited += 0.1
        if waited > timeout:
            raise AssertionError("condition not reached")


def _states(db: Path, kind: str) -> dict[str, str]:
    store = SQLiteStore(db)
    try:
        return EvidenceStore(store).states(kind)
    finally:
        store.close()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    batch = generate_batch(seed=5, runs=300)
    store = SQLiteStore(tmp_path / DB_NAME)
    try:
        import_batch(store, batch)
        extract_pairs(EvidenceStore(store), parse_batch(batch).valid)
    finally:
        store.close()
    return tmp_path


def test_tabs_render_on_an_empty_workspace_without_creating_a_database(tmp_path: Path):
    async def scenario():
        app = ParakhApp(data_dir=tmp_path, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(170, 50)) as pilot:
            await _until(pilot, lambda: app.state is not None)
            for key in "tpo":
                await pilot.press(key)
            await pilot.pause(0.3)
            assert app.query_one("#cand-table", DataTable).row_count == 0
            assert "No telemetry imported" in str(app.query_one("#cand-intake").render())
    asyncio.run(scenario())
    assert not (tmp_path / DB_NAME).exists()


def test_candidate_review_needs_a_named_operator_and_records_the_role(workspace: Path):
    db = workspace / DB_NAME
    async def scenario():
        app = ParakhApp(data_dir=workspace, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(170, 50)) as pilot:
            await pilot.press("t")
            table = app.query_one("#cand-table", DataTable)
            await _until(pilot, lambda: table.row_count > 0)
            table.move_cursor(row=0)
            await pilot.pause(0.2)
            view_candidate = app.query_one("#cand-table", DataTable).coordinate_to_cell_key((0, 0)).row_key.value
            assert "lineage: run" in str(app.query_one("#cand-detail").render())
            app.query_one("#cand-role", Select).value = "REGRESSION"
            app.query_one("#btn-cand-approve", Button).press()  # no actor/reason yet
            await pilot.pause(0.5)
            assert _states(db, "evaluation_candidate")[view_candidate] == "VALIDATED"
            app.query_one("#cand-actor", Input).value = "ops-lead"
            app.query_one("#cand-reason", Input).value = "novel failure signature"
            app.query_one("#btn-cand-approve", Button).press()
            await _until(pilot, lambda: _states(db, "evaluation_candidate")[view_candidate] == "REGRESSION")
            return view_candidate
    approved = asyncio.run(scenario())
    store = SQLiteStore(db)
    try:
        history = EvidenceStore(store).history("evaluation_candidate", approved)
    finally:
        store.close()
    assert [h["to_state"] for h in history][-2:] == ["APPROVED", "REGRESSION"] and history[-1]["actor"] == "ops-lead"


def test_candidate_review_controls_fit_a_standard_terminal(workspace: Path):
    async def scenario():
        app = ParakhApp(data_dir=workspace, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(160, 44)) as pilot:
            await pilot.press("t")
            table = app.query_one("#cand-table", DataTable)
            await _until(pilot, lambda: table.row_count > 24)
            await pilot.pause(0.2)
            controls = ("#cand-actor", "#cand-reason", "#cand-role", "#btn-cand-approve", "#btn-cand-reject")
            assert all(app.query_one(selector).region.bottom < app.size.height - 1 for selector in controls)

    asyncio.run(scenario())


def test_ambiguous_preference_pair_is_classified_then_approved_by_an_operator(workspace: Path):
    db = workspace / DB_NAME
    waiting = [pid for pid, state in _states(db, "preference_pair").items() if state == "NEEDS_REVIEW"]
    assert waiting, "fixture should contain pairs that need a human decision"

    async def scenario():
        app = ParakhApp(data_dir=workspace, suite_path=SUITE, poll_seconds=0.1)
        async with app.run_test(size=(170, 50)) as pilot:
            await pilot.press("p")
            table = app.query_one("#pref-table", DataTable)
            await _until(pilot, lambda: table.row_count > 0)
            keys = [table.coordinate_to_cell_key((i, 0)).row_key.value for i in range(table.row_count)]
            table.move_cursor(row=keys.index(waiting[0]))
            await pilot.pause(0.2)
            assert "chosen" in str(app.query_one("#pref-detail").render())
            app.query_one("#pref-actor", Input).value = "reviewer-1"
            app.query_one("#pref-reason", Input).value = "genuine factual correction"
            app.query_one("#btn-pref-approve", Button).press()  # NEEDS_REVIEW cannot jump to APPROVED
            await pilot.pause(0.5)
            assert _states(db, "preference_pair")[waiting[0]] == "NEEDS_REVIEW"
            app.query_one("#btn-pref-propose", Button).press()
            await _until(pilot, lambda: _states(db, "preference_pair")[waiting[0]] == "PROPOSED")
            app.query_one("#btn-pref-approve", Button).press()
            await _until(pilot, lambda: _states(db, "preference_pair")[waiting[0]] == "APPROVED")
            await pilot.press("o")
            await pilot.pause(0.3)
            assert "No policy candidates" in str(app.query_one("#policy-detail").render())
    asyncio.run(scenario())
