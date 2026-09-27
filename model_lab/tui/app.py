"""Parakh ModelLab console: a Textual app over the observability read model.

Threading model: actions run on worker threads with their own SQLite
connection and write runs/attempts/events; a refresh worker rebuilds
``ConsoleState`` from the database every ``POLL_SECONDS`` when new events
exist. The UI thread only renders state — every number shown comes from the
store, so progress reflects real execution.
"""

from __future__ import annotations

import asyncio
import signal
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, RichLog, Select, Static, TabbedContent, TabPane

from model_lab.application import lab_actions
from model_lab.application import optimization_console as optimization
from model_lab.application.observability import open_store
from model_lab.errors import ModelLabError
from model_lab.providers.fake import FakeVariant
from model_lab.tui import formatting as fmt
from model_lab.tui.state import ConsoleState, SuiteCache, build_state
from model_lab.tui.views import (
    CandidateReviewView, CasesView, CompareView, DashboardView, ModelsView, PolicyView, PreferenceReviewView, ResultsView,
    ReviewView, RoutingView, RunDetailView, RunsView, SuitesView, event_line,
)

POLL_SECONDS = 0.5
TABS = (
    ("1", "dashboard", "Dashboard"), ("2", "suites", "Suites"), ("3", "cases", "Cases"), ("4", "models", "Models"),
    ("5", "runs", "Runs"), ("6", "run", "Run detail"), ("7", "results", "Results"), ("8", "compare", "Compare"),
    ("9", "review", "Review"), ("0", "routing", "Routing"), ("t", "candidates", "Candidates"), ("p", "preferences", "Preferences"),
    ("o", "policies", "Policies"), ("l", "events", "Events"),
)


class FakeRunScreen(ModalScreen[dict[str, Any] | None]):
    """Configure an offline fake-provider run (never paid, never networked)."""

    DEFAULT_CSS = """
    FakeRunScreen { align: center middle; }
    #fake-dialog { width: 76; height: auto; padding: 1 2; border: thick $primary; background: $surface; grid-size: 2; grid-columns: 22 1fr; grid-rows: auto; grid-gutter: 1; }
    #fake-dialog Label { padding-top: 1; }
    #fake-title { column-span: 2; }
    #fake-buttons { column-span: 2; height: auto; align: right middle; }
    """
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Grid(id="fake-dialog"):
            yield Static("[b]Start fake-provider run[/] [magenta]SIMULATED[/] — offline, no credentials, no cost", id="fake-title", markup=True)
            yield Label("model label")
            yield Input("synthetic-v1", id="fake-model")
            yield Label("variant")
            yield Select([(v.value, v.value) for v in FakeVariant], value=FakeVariant.CORRECT.value, allow_blank=False, id="fake-variant")
            yield Label("max cases (blank=all)")
            yield Input("20", id="fake-cases", type="integer")
            yield Label("fail first N calls/case")
            yield Input("0", id="fake-fail", type="integer")
            yield Label("max retries")
            yield Input("0", id="fake-retries", type="integer")
            yield Label("pacing seconds/case")
            yield Input(str(lab_actions.DEFAULT_PACING_SECONDS * 3), id="fake-pacing", type="number")
            with Horizontal(id="fake-buttons"):
                yield Button("Cancel", id="fake-cancel")
                yield Button("Start", id="fake-start", variant="primary")

    def _int(self, widget_id: str, default: int | None) -> int | None:
        raw = self.query_one(widget_id, Input).value.strip()
        return int(raw) if raw else default

    @on(Button.Pressed, "#fake-start")
    def start(self) -> None:
        try:
            config = {
                "model": self.query_one("#fake-model", Input).value.strip() or "synthetic-v1",
                "variant": str(self.query_one("#fake-variant", Select).value),
                "max_cases": self._int("#fake-cases", None),
                "fail_times": self._int("#fake-fail", 0) or 0,
                "max_retries": self._int("#fake-retries", 0) or 0,
                "pacing_seconds": float(self.query_one("#fake-pacing", Input).value or 0),
            }
        except ValueError as exc:
            self.notify(f"invalid value: {exc}", severity="error")
            return
        self.dismiss(config)

    @on(Button.Pressed, "#fake-cancel")
    def action_cancel(self) -> None:
        self.dismiss(None)


class ParakhApp(App[None]):
    TITLE = "Parakh ModelLab"
    SUB_TITLE = "offline-first evaluation console"
    CSS = """
    #statusbar { height: 1; padding: 0 1; background: $boost; }
    .row { height: auto; }
    .row Panel { width: 1fr; }
    .buttons { height: auto; margin: 0 0 1 0; }
    .buttons Input { width: 1fr; }
    .buttons Select { width: 1fr; }
    .buttons Button { margin-right: 1; }
    DataTable { height: auto; max-height: 24; }
    #cases-table, #runs-table, #review-table { height: 1fr; max-height: 100%; }
    #cand-table, #pref-table { height: 1fr; min-height: 4; max-height: 12; }
    #event-log { height: 1fr; }
    """
    BINDINGS = [
        *(Binding(key, f"tab('{tab_id}')", label, show=key in {"1", "5", "l"}) for key, tab_id, label in TABS),
        Binding("d", "demo", "Demo run"),
        Binding("f", "fake_run", "Fake run"),
        Binding("g", "grade", "Grade"),
        Binding("v", "validate", "Validate", show=False),
        Binding("h", "doctor", "Doctor", show=False),
        Binding("x", "cancel_run", "Cancel run", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, *, data_dir: str | Path = "lab-data/tui", suite_path: str | Path = "benchmarks/seed_cases.jsonl",
                 demo: bool = False, plan_path: str | None = None, poll_seconds: float = POLL_SECONDS) -> None:
        super().__init__()
        self.data_dir, self.suite_path = Path(data_dir), Path(suite_path)
        self.start_demo, self.plan_path, self.poll_seconds = demo, plan_path, poll_seconds
        self.suites = SuiteCache()
        self.state: ConsoleState | None = None
        self.selected_run_id: str | None = None
        self.last_event_id = 0
        self.cancel_event: threading.Event | None = None  # the console's current fake run ('x')
        self.run_events: list[threading.Event] = []  # every running execution; set on quit so workers end promptly
        self._dirty = True
        self.busy: set[str] = set()
        self._built = 0  # monotonically increasing build number; stale builds are dropped
        self._applied = 0
        self._seq_lock = threading.Lock()
        self.session: dict[str, Any] = {}  # preflight/comparison results survive state rebuilds

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="statusbar", markup=True)
        with TabbedContent(initial="dashboard", id="tabs"):
            with TabPane("1 Dashboard", id="dashboard"):
                yield DashboardView()
            with TabPane("2 Suites", id="suites"):
                yield SuitesView()
            with TabPane("3 Cases", id="cases"):
                yield CasesView()
            with TabPane("4 Models", id="models"):
                yield ModelsView()
            with TabPane("5 Runs", id="runs"):
                yield RunsView()
            with TabPane("6 Run detail", id="run"):
                yield RunDetailView()
            with TabPane("7 Results", id="results"):
                yield ResultsView()
            with TabPane("8 Compare", id="compare"):
                yield CompareView()
            with TabPane("9 Review", id="review"):
                yield ReviewView()
            with TabPane("0 Routing", id="routing"):
                yield RoutingView()
            with TabPane("t Candidates", id="candidates"):
                yield CandidateReviewView()
            with TabPane("p Preferences", id="preferences"):
                yield PreferenceReviewView()
            with TabPane("o Policies", id="policies"):
                yield PolicyView()
            with TabPane("l Events", id="events"):
                yield RichLog(id="event-log", max_lines=2000, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        # `parakh stop` / closing the terminal: exit through Textual so the terminal is restored.
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGHUP):
            try:
                loop.add_signal_handler(sig, self.shutdown)
            except (NotImplementedError, RuntimeError, ValueError):  # non-main thread or unsupported platform
                pass
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.set_interval(self.poll_seconds, self.poll)
        self.refresh_state(force=True)
        if self.plan_path:
            self.preflight(self.plan_path)
        if self.start_demo:
            self.maybe_start_demo()

    # ------------------------------------------------------------------ state
    def poll(self) -> None:
        self.refresh_state(force=False)

    def _latest_event_id(self) -> int:
        store = open_store(self.data_dir)
        if store is None:
            return 0
        try:
            events = store.list_events(limit=1)
            return events[-1].event_id or 0 if events else 0
        finally:
            store.close()

    @work(thread=True, exclusive=True, group="refresh", exit_on_error=False)
    def refresh_state(self, force: bool = False) -> None:
        try:
            self._refresh(force)
        except (sqlite3.Error, ModelLabError, OSError):
            # e.g. "database is locked" while an action is creating the DB; retry next tick
            self._dirty = True

    def _refresh(self, force: bool) -> None:
        latest = self._latest_event_id()
        running = bool(self.state and self.state.snapshot.active)
        if not (force or self._dirty or running or latest != self.last_event_id):
            return
        self._dirty = False
        with self._seq_lock:
            self._built += 1
            seq = self._built
        state = build_state(self.data_dir, self.suite_path, self.suites, selected_run_id=self.selected_run_id)
        self.call_from_thread(self.apply_state, state, seq)

    def apply_state(self, state: ConsoleState, seq: int = 0) -> None:
        if seq and seq < self._applied:
            return
        self._applied = max(self._applied, seq)
        for key, value in self.session.items():
            setattr(state, key, value)
        self.state = state
        run_ids = {run.run_id for run in state.snapshot.runs}
        if self.selected_run_id not in run_ids and state.selected_run is not None:
            self.selected_run_id = state.selected_run.run_id  # adopt the default only when nothing valid is selected
        elif state.selected_run is not None and state.selected_run.run_id != self.selected_run_id:
            self._dirty = True  # built for an older selection; the next tick rebuilds for the current one
        for view_type in (DashboardView, SuitesView, CasesView, ModelsView, RunsView, RunDetailView, ResultsView, CompareView, ReviewView, RoutingView,
                          CandidateReviewView, PreferenceReviewView, PolicyView):
            try:
                self.query_one(view_type).show(state)
            except Exception as exc:  # a rendering bug must not kill the console; surface it
                self.notify(f"{view_type.__name__}: {type(exc).__name__}: {exc}", severity="error", timeout=8)
        log = self.query_one("#event-log", RichLog)
        new = [e for e in state.snapshot.events if (e.event_id or 0) > self.last_event_id]
        for event in new:
            log.write(event_line(event))
        if new:
            self.last_event_id = new[-1].event_id or self.last_event_id
        snap = state.snapshot
        active = f"[yellow]● running {len(snap.active)}[/]" if snap.active else "[green]idle[/]"
        health = "[green]healthy[/]" if snap.health.get("offline_ready") else "[red]doctor: not ready[/]"
        busy = f"  [cyan]working: {', '.join(sorted(self.busy))}[/]" if self.busy else ""
        self.query_one("#statusbar", Static).update(
            f"{health}  {active}  runs {len(snap.runs)}  suite {fmt.text(snap.suite.version if snap.suite else None)}  "
            f"db {fmt.text(snap.db_path)}  selected {fmt.text(self.selected_run_id, 'none')}{busy}")

    def mark_dirty(self) -> None:
        self._dirty = True
        self.refresh_state(force=True)

    # ------------------------------------------------------------------ actions
    def start_action(self, name: str, fn: Callable[[], Any], done: Callable[[Any], str]) -> None:
        if name in self.busy:
            self.notify(f"{name} already running", severity="warning")
            return
        self.busy.add(name)
        self.notify(f"{name} started")
        self._background(name, fn, done)

    @work(thread=True, group="actions")
    def _background(self, name: str, fn: Callable[[], Any], done: Callable[[Any], str]) -> None:
        try:
            result = fn()
            self.call_from_thread(self.notify, done(result), timeout=6)
        except (ModelLabError, OSError, ValueError) as exc:
            self.call_from_thread(self.notify, f"{name} failed: {exc}", severity="error", timeout=10)
        finally:
            self.busy.discard(name)
            self.call_from_thread(self.mark_dirty)

    def maybe_start_demo(self) -> None:
        store = open_store(self.data_dir)
        has_runs = False
        if store is not None:
            try:
                has_runs = bool(store.list_run_ids())
            finally:
                store.close()
        if not has_runs:
            self.action_demo()

    def action_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh(self) -> None:
        self.mark_dirty()

    def _new_cancel_event(self) -> threading.Event:
        event = threading.Event()
        self.run_events.append(event)
        return event

    def shutdown(self) -> None:
        """Quit: stop executions before the next case (runs end 'cancelled'), then exit and restore the terminal."""
        for event in self.run_events:
            event.set()
        self.exit()

    async def action_quit(self) -> None:
        self.shutdown()

    def action_demo(self) -> None:
        cancel = self._new_cancel_event()
        self.start_action("offline demo", lambda: lab_actions.run_demo(self.data_dir, self.suite_path, cancel_event=cancel),
                        lambda r: f"DEMO finished: {len(r['runs'])} SIMULATED runs, comparison + draft routing written")

    def action_fake_run(self) -> None:
        def start(config: dict[str, Any] | None) -> None:
            if config is None:
                return
            self.cancel_event = cancel = self._new_cancel_event()
            self.start_action("fake run", lambda: lab_actions.run_fake(self.data_dir, self.suite_path, cancel_event=cancel, **config),
                            lambda r: f"fake run {r['run_id']}: {r['status']}, {r['attempts']} attempts, {r['failures']} failed")
        self.push_screen(FakeRunScreen(), start)

    def action_cancel_run(self) -> None:
        if self.cancel_event is None or "fake run" not in self.busy:
            self.notify("no cancellable TUI run is active", severity="warning")
            return
        self.cancel_event.set()
        self.notify("cancellation requested; the engine stops before the next case")

    def action_grade(self) -> None:
        run_id = self.selected_run_id
        if run_id is None:
            self.notify("select a run first (Runs tab)", severity="warning")
            return
        self.start_action("grading", lambda: lab_actions.grade_ungraded(self.data_dir, self.suite_path, run_id),
                        lambda n: f"graded {n} attempts in {run_id}" if n else f"{run_id}: nothing left to grade")

    def action_validate(self) -> None:
        self.start_action("validate", lambda: lab_actions.validate(self.data_dir, self.suite_path),
                        lambda r: f"suite valid: {r['cases']} cases, {r['families']} families, {r['domains']} domains")

    def action_doctor(self) -> None:
        self.suites.invalidate()
        self.start_action("doctor", lambda: lab_actions.doctor(self.data_dir, self.suite_path),
                        lambda r: "doctor: offline ready" if r.get("offline_ready") else f"doctor: NOT ready {r}")

    def preflight(self, plan_path: str) -> None:
        def done(result: dict[str, Any]) -> str:
            self.call_from_thread(self._set_preflight, result)
            return "preflight complete — paid dispatch stays disabled in the TUI"
        self.start_action("preflight", lambda: lab_actions.pilot_preflight(plan_path), done)

    def _set_preflight(self, result: dict[str, Any]) -> None:
        self.session["preflight"] = result
        if self.state is not None:
            self.state.preflight = result
            self.query_one(ModelsView).show(self.state)

    def _set_comparison(self, payload: tuple[Any, list[dict[str, Any]], tuple[str, str]]) -> None:
        self.session.update(comparison=payload[0], routing=payload[1], comparison_runs=payload[2])
        if self.state is not None:
            self.state.comparison, self.state.routing, self.state.comparison_runs = payload
            for view_type in (CompareView, RoutingView, DashboardView):
                self.query_one(view_type).show(self.state)

    # ------------------------------------------------------------------ widget events
    @on(Button.Pressed, "#btn-demo")
    def _btn_demo(self) -> None:
        self.action_demo()

    @on(Button.Pressed, "#btn-fake")
    def _btn_fake(self) -> None:
        self.action_fake_run()

    @on(Button.Pressed, "#btn-grade")
    def _btn_grade(self) -> None:
        self.action_grade()

    @on(Button.Pressed, "#btn-cancel")
    def _btn_cancel(self) -> None:
        self.action_cancel_run()

    @on(Button.Pressed, "#btn-validate")
    def _btn_validate(self) -> None:
        self.action_validate()

    @on(Button.Pressed, "#btn-preflight")
    def _btn_preflight(self) -> None:
        path = self.query_one("#plan-path", Input).value.strip()
        if not path:
            self.notify("enter a plan path", severity="warning")
            return
        self.preflight(path)

    @on(Button.Pressed, "#btn-import")
    def _btn_import(self) -> None:
        path, run_id = self.query_one("#import-path", Input).value.strip(), self.selected_run_id
        if not path or run_id is None:
            self.notify("select a run and enter a file path", severity="warning")
            return
        self.start_action("import", lambda: lab_actions.import_results(self.data_dir, run_id, path),
                        lambda r: f"import into {run_id}: {r['imported']} imported, {r['quarantined']} quarantined, {r['duplicates']} duplicates")

    @on(Button.Pressed, "#btn-compare")
    def _btn_compare(self) -> None:
        left, right = self.query_one("#cmp-left", Select).value, self.query_one("#cmp-right", Select).value
        if not isinstance(left, str) or not isinstance(right, str):
            self.notify("choose two runs", severity="warning")
            return

        def compute() -> tuple[Any, list[dict[str, Any]], tuple[str, str]]:
            comparison, routing = lab_actions.compare_runs(self.data_dir, self.suite_path, left, right)
            payload = (comparison, routing, (left, right))
            self.call_from_thread(self._set_comparison, payload)
            return payload
        self.start_action("compare", compute, lambda p: f"compared {p[0].matched_cases} matched cases; {len(p[1])} PROPOSED drafts")

    @on(DataTable.RowSelected, "#runs-table")
    def _open_run(self, event: DataTable.RowSelected) -> None:
        self.selected_run_id = str(event.row_key.value)
        self.action_tab("run")
        self.mark_dirty()

    @on(DataTable.RowHighlighted, "#runs-table")
    def _highlight_run(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key.value and event.row_key.value != self.selected_run_id:
            self.selected_run_id = str(event.row_key.value)
            self.mark_dirty()

    @on(DataTable.RowHighlighted, "#cases-table")
    def _show_case(self, event: DataTable.RowHighlighted) -> None:
        if self.state is not None and event.row_key.value:
            self.query_one(CasesView).show_case(self.state, str(event.row_key.value))

    @on(DataTable.RowHighlighted, "#review-table")
    def _show_review(self, event: DataTable.RowHighlighted) -> None:
        if self.state is not None and event.row_key.value:
            self.query_one(ReviewView).show_item(self.state, str(event.row_key.value))

    @on(Input.Changed, "#case-filter")
    def _filter_cases(self) -> None:
        if self.state is not None:
            self.query_one(CasesView).show(self.state)

    # ------------------------------------------------------------------ optimization review (operator-only)
    @on(DataTable.RowHighlighted, "#cand-table")
    def _show_candidate(self, event: DataTable.RowHighlighted) -> None:
        if self.state is not None and event.row_key.value:
            views = self.query(CandidateReviewView).nodes
            if views:  # A queued highlight can outlive its tab during shutdown.
                views[0].show_item(self.state, str(event.row_key.value))

    @on(DataTable.RowHighlighted, "#pref-table")
    def _show_pair(self, event: DataTable.RowHighlighted) -> None:
        if self.state is not None and event.row_key.value:
            views = self.query(PreferenceReviewView).nodes
            if views:
                views[0].show_item(self.state, str(event.row_key.value))

    @on(DataTable.RowHighlighted, "#policy-table")
    def _show_policy(self, event: DataTable.RowHighlighted) -> None:
        if self.state is not None and event.row_key.value:
            views = self.query(PolicyView).nodes
            if views:
                views[0].show_item(self.state, str(event.row_key.value))

    def _operator_fields(self, prefix: str) -> tuple[str, str]:
        return self.query_one(f"#{prefix}-actor", Input).value, self.query_one(f"#{prefix}-reason", Input).value

    @on(Button.Pressed, "#btn-cand-approve, #btn-cand-reject")
    def _review_candidate(self, event: Button.Pressed) -> None:
        candidate_id = self.query_one(CandidateReviewView).selected
        if candidate_id is None:
            self.notify("highlight a candidate first", severity="warning")
            return
        decision = "approve" if event.button.id == "btn-cand-approve" else "reject"
        role = self.query_one("#cand-role", Select).value
        actor, reason = self._operator_fields("cand")
        self.start_action(f"candidate {decision}", lambda: optimization.review_candidate(
            self.data_dir, candidate_id, decision, role=role if isinstance(role, str) else None, actor=actor, reason=reason),
            lambda t: f"{t['entity_id']}: {t['from_state']} -> {t['to_state']} by {t['actor']}")

    @on(Button.Pressed, "#btn-pref-propose, #btn-pref-approve, #btn-pref-reject")
    def _review_pair(self, event: Button.Pressed) -> None:
        pair_id = self.query_one(PreferenceReviewView).selected
        if pair_id is None:
            self.notify("highlight a preference pair first", severity="warning")
            return
        decision = str(event.button.id).removeprefix("btn-pref-")
        actor, reason = self._operator_fields("pref")
        self.start_action(f"pair {decision}", lambda: optimization.review_preference(self.data_dir, pair_id, decision, actor=actor, reason=reason),
                          lambda t: f"{t['entity_id']}: {t['from_state']} -> {t['to_state']} by {t['actor']}")


def run_tui(*, data_dir: str | Path, suite_path: str | Path, demo: bool = False, plan_path: str | None = None) -> int:
    ParakhApp(data_dir=data_dir, suite_path=suite_path, demo=demo, plan_path=plan_path).run()
    return 0
