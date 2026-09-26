"""One widget per console tab. Each renders a ``ConsoleState``; none touches storage."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Select, Static

from model_lab.application.observability import BreakdownRow
from model_lab.tui import formatting as fmt
from model_lab.tui.state import ConsoleState

SPARSE_NOTE = ("[dim]Sparse, fixture-level benchmark: category results describe these cases only. "
               "They do not rank models universally.[/]")


def sync_table(table: DataTable, rows: Sequence[tuple[str, Sequence[Any]]]) -> None:
    """Replace rows only when content changed; keep the cursor on the same key."""
    signature = hash(tuple((key, tuple(map(str, cells))) for key, cells in rows))
    if getattr(table, "_signature", None) == signature:
        return
    table._signature = signature  # type: ignore[attr-defined]
    current = None
    if table.row_count and table.cursor_row is not None and 0 <= table.cursor_row < table.row_count:
        current = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value
    table.clear()
    for key, cells in rows:
        table.add_row(*cells, key=key)
    keys = [key for key, _ in rows]
    if current in keys:
        table.move_cursor(row=keys.index(current))


def make_table(id_: str, columns: Iterable[str]) -> DataTable:
    table = DataTable(id=id_, cursor_type="row", zebra_stripes=True)
    table.add_columns(*columns)
    return table


def breakdown_rows(rows: list[BreakdownRow]) -> list[tuple[str, list[str]]]:
    return [(row.group, [fmt.text(row.group), str(row.graded), str(row.passed), str(row.failed), str(row.abstained),
                         str(row.attempt_failures), fmt.pct(row.pass_rate)]) for row in rows]


BREAKDOWN_COLUMNS = ("group", "graded", "passed", "failed", "needs review", "attempt failures", "pass rate (decided)")


class Panel(Static):
    """Bordered text panel."""

    DEFAULT_CSS = "Panel { border: round $primary-darken-2; padding: 0 1; height: auto; }"

    def __init__(self, title: str, **kwargs: Any) -> None:
        super().__init__("", markup=True, **kwargs)
        self.border_title = title


class DashboardView(VerticalScroll):
    def compose(self) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Panel("Workspace", id="dash-workspace")
            yield Panel("Health (doctor)", id="dash-health")
            yield Panel("Runs", id="dash-runs")
        with Horizontal(classes="row"):
            yield Panel("Latest run", id="dash-latest")
            yield Panel("Active execution", id="dash-active")
        with Horizontal(classes="row"):
            yield Panel("Providers", id="dash-providers")
            yield Panel("Routing", id="dash-routing")
        yield Panel("Recent events", id="dash-events")

    def show(self, state: ConsoleState) -> None:
        snap = state.snapshot
        suite = snap.suite
        self.query_one("#dash-workspace", Panel).update(
            f"data dir  {fmt.text(snap.data_dir)}\n"
            f"database  {'[green]present[/]' if snap.db_exists else '[yellow]not created yet (run an action)[/]'}\n"
            f"suite     {fmt.text(suite.path if suite else None)}\n"
            f"version   {fmt.text(suite.version if suite else None)}\n"
            f"cases     {suite.cases if suite else fmt.NA}"
            + (f"\n[red]error: {fmt.text(snap.error)}[/]" if snap.error else "")
            + (f"\n[red]suite: {fmt.text(state.suite_error)}[/]" if state.suite_error else ""))
        health = "\n".join(f"{'[green]✔[/]' if v is True else '[red]✘[/]' if v is False else '•'} {fmt.text(k)} {'' if isinstance(v, bool) else fmt.text(v)}"
                           for k, v in snap.health.items())
        self.query_one("#dash-health", Panel).update(health or fmt.NA)
        self.query_one("#dash-runs", Panel).update(
            f"total          {len(snap.runs)}\ncompleted      {snap.completed_runs}\n"
            f"failed/partial {snap.failed_runs}\nrunning        {len(snap.active)}\n"
            f"needs review   {snap.review_pending} [dim](abstained+failed+ungraded)[/]")
        latest = snap.runs[0] if snap.runs else None
        if latest is None:
            self.query_one("#dash-latest", Panel).update("No runs yet. Press [b]d[/] for the offline DEMO or [b]f[/] for a fake-provider run.")
        else:
            self.query_one("#dash-latest", Panel).update(
                f"{fmt.text(latest.run_id)}  {fmt.styled(latest.provenance, fmt.PROVENANCE_STYLE)}\n"
                f"model {fmt.text(latest.model)} via {fmt.text(latest.provider)}   status {fmt.styled(latest.status)}\n"
                f"pass rate {fmt.pct(latest.pass_rate)} ({latest.passed} passed / {latest.failed_grades} failed / {latest.abstained} needs review)\n"
                f"cost {fmt.text(fmt.cost(latest.cost))}   latency {fmt.ms(latest.latency_ms_mean)}   duration {fmt.seconds(latest.duration_seconds)}")
        if snap.active:
            lines = []
            for active in snap.active:
                lines.append(f"[yellow]● {fmt.text(active.run_id)}[/] {fmt.text(active.model)} via {fmt.text(active.provider)}\n"
                             f"  {fmt.bar(active.completed, active.total)}  failures {active.failures}  retries {active.retries}  "
                             f"elapsed {fmt.seconds(active.elapsed_seconds)}\n  now: {fmt.text(active.current_operation)}")
            self.query_one("#dash-active", Panel).update("\n".join(lines))
        else:
            self.query_one("#dash-active", Panel).update("[dim]idle — no run is executing[/]")
        providers = "\n".join(f"{fmt.text(p.provider):<11} {fmt.text(p.availability)}" for p in snap.providers[:3])
        self.query_one("#dash-providers", Panel).update(providers)
        if state.routing:
            eligible = sum(bool(r.get("eligibility")) for r in state.routing)
            routing = (f"[cyan]PROPOSED draft[/] from last comparison: {len(state.routing)} candidates, {eligible} eligible\n"
                       "No router configuration is ever written.")
        else:
            routing = "No draft routing evidence in this session (Compare tab → Compare). Router config is never written."
        self.query_one("#dash-routing", Panel).update(routing)
        self.query_one("#dash-events", Panel).update(
            "\n".join(event_line(e) for e in snap.events[-12:]) or "[dim]no events recorded[/]")


def event_line(event: Any) -> str:
    parts = [f"[dim]{fmt.clock(event.timestamp)}[/]", fmt.styled(event.event_type.replace("_", " "), {}),]
    if event.run_id:
        parts.append(f"[dim]{fmt.text(fmt.truncate(event.run_id, 34))}[/]")
    parts.append(fmt.text(event.message))
    if event.duration_ms is not None:
        parts.append(f"[dim]{event.duration_ms:.1f}ms[/]")
    if event.error:
        parts.append(f"[red]{fmt.text(fmt.truncate(event.error, 120))}[/]")
    return " ".join(parts)


class SuitesView(Vertical):
    def compose(self) -> ComposeResult:
        yield make_table("suites-table", ("suite file", "version", "cases", "families", "status"))
        with Horizontal(classes="buttons"):
            yield Button("Validate active suite (v)", id="btn-validate", variant="primary")
        yield Panel("Active suite distribution", id="suite-detail")

    def show(self, state: ConsoleState) -> None:
        snap = state.snapshot
        rows = []
        for path in snap.suites or ([snap.suite.path] if snap.suite else []):
            summary = snap.suite if snap.suite and snap.suite.path == path else None
            rows.append((path, [fmt.text(path), fmt.text(summary.version if summary else "(not loaded)"),
                                str(summary.cases) if summary else fmt.NA, str(summary.families) if summary else fmt.NA,
                                "active" if summary else "available"]))
        sync_table(self.query_one("#suites-table", DataTable), rows)
        suite = snap.suite
        if suite is None:
            self.query_one("#suite-detail", Panel).update("[yellow]No suite file found at the configured path.[/]")
            return
        if suite.error:
            self.query_one("#suite-detail", Panel).update(f"[red]{fmt.text(suite.error)}[/]")
            return
        domains = "  ".join(f"{fmt.text(k)}:{v}" for k, v in suite.domains.items())
        complexity = "  ".join(f"L{k}:{v}" for k, v in suite.complexity.items())
        splits = "  ".join(f"{fmt.text(k)}:{v}" for k, v in suite.splits.items())
        self.query_one("#suite-detail", Panel).update(
            f"version {fmt.text(suite.version)}  hash {fmt.text((suite.source_hash or '')[:16])}…  cases {suite.cases}  families {suite.families}\n"
            f"[b]by domain[/]      {domains}\n[b]by complexity[/]  {complexity}\n"
            f"[b]by split[/]       {splits}  [dim](train = development, calibration, holdout = sealed)[/]")


class CasesView(Vertical):
    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter: case id, domain, split, family, status…", id="case-filter")
        yield make_table("cases-table", ("case", "domain", "L", "split", "family", "method", "latest status", "grade"))
        yield Panel("Case (candidate-safe metadata only; references/rubrics are never shown)", id="case-detail")

    def show(self, state: ConsoleState) -> None:
        needle = self.query_one("#case-filter", Input).value.strip().lower()
        rows = []
        for case in state.cases:
            haystack = " ".join((case.case_id, case.domain, case.split, case.family_id, case.latest_status, case.latest_grade, *case.tags)).lower()
            if needle and needle not in haystack:
                continue
            rows.append((case.case_id, [fmt.text(case.case_id), fmt.text(case.domain), str(case.complexity_level), fmt.text(case.split),
                                        fmt.text(fmt.truncate(case.family_id, 28)), fmt.text(case.evaluation_method),
                                        fmt.styled(case.latest_status), fmt.styled(case.latest_grade)]))
        sync_table(self.query_one("#cases-table", DataTable), rows)
        run = state.selected_run
        self.border_subtitle = f"status shown for run {run.run_id}" if run else "no run selected"

    def show_case(self, state: ConsoleState, case_id: str) -> None:
        case = next((c for c in state.cases if c.case_id == case_id), None)
        if case is None:
            return
        self.query_one("#case-detail", Panel).update(
            f"[b]{fmt.text(case.case_id)}[/]  family {fmt.text(case.family_id)}  domain {fmt.text(case.domain)}  "
            f"complexity L{case.complexity_level}  split {fmt.text(case.split)}  language {fmt.text(case.language)}\n"
            f"tags {fmt.text(', '.join(case.tags))}  evaluation method {fmt.text(case.evaluation_method)}  messages {case.message_count}\n"
            f"latest status {fmt.styled(case.latest_status)}  grade {fmt.styled(case.latest_grade)}\n"
            f"[dim]prompt:[/] {fmt.text(fmt.truncate(case.prompt_preview, 400))}")


class ModelsView(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield make_table("models-table", ("provider", "model", "availability", "configuration", "capabilities", "experiment eligibility", "runs"))
        yield Panel("Live pilot preflight (read-only)", id="pilot-help")
        with Horizontal(classes="buttons"):
            yield Input(placeholder="path to pilot plan JSON", id="plan-path")
            yield Button("Preflight plan", id="btn-preflight")
        yield Panel("Preflight result", id="pilot-result")

    def show(self, state: ConsoleState) -> None:
        rows = [(f"{p.provider}:{p.model}", [fmt.text(p.provider), fmt.text(p.model), fmt.text(p.availability), fmt.text(p.configuration),
                                            fmt.text(p.capabilities), fmt.text(p.eligibility), str(p.measured_runs)])
                for p in state.snapshot.providers]
        sync_table(self.query_one("#models-table", DataTable), rows)
        self.query_one("#pilot-help", Panel).update(
            "Paid/live execution is [b]never started from the TUI[/]. Preflight shows what a plan would dispatch and "
            "why the gate is closed. Dispatch requires a verified immutable plan and "
            "`model-lab pilot run … --allow-paid` in a terminal.")
        pre = state.preflight
        if pre is None:
            self.query_one("#pilot-result", Panel).update("[dim]no plan preflighted[/]")
            return
        preview = pre["preview"]
        self.query_one("#pilot-result", Panel).update(
            f"paid dispatch from TUI: [red]disabled[/]\n"
            f"candidates {fmt.text(preview.get('candidate_models'))}\n"
            f"cases {len(preview.get('case_ids') or [])}  base calls {fmt.text(preview.get('base_calls'))}  max calls {fmt.text(preview.get('maximum_calls'))}\n"
            f"budget {fmt.text(preview.get('budget'))}\n"
            f"plan blockers {fmt.text(', '.join(pre['plan_blockers']) or 'none')}\n"
            f"gate [yellow]{fmt.text(pre['gate'])}[/]\n"
            f"to dispatch: {fmt.text(pre['how_to_dispatch'])}")


RUN_COLUMNS = ("run", "evidence", "model", "provider", "status", "started", "duration", "cases", "failed", "pass rate", "graded", "cost", "latency")


class RunsView(Vertical):
    def compose(self) -> ComposeResult:
        with Horizontal(classes="buttons"):
            yield Button("Offline demo (d)", id="btn-demo", variant="primary")
            yield Button("Fake run… (f)", id="btn-fake")
            yield Button("Grade selected (g)", id="btn-grade")
            yield Button("Cancel TUI run (x)", id="btn-cancel", variant="error")
        yield make_table("runs-table", RUN_COLUMNS)
        yield Static("[dim]Enter opens run detail. Evidence: SIMULATED = fake provider, IMPORTED = ingested, MEASURED = live provider.[/]", markup=True)

    def show(self, state: ConsoleState) -> None:
        rows = []
        for run in state.snapshot.runs:
            rows.append((run.run_id, [fmt.text(fmt.truncate(run.run_id, 40)), fmt.styled(run.provenance, fmt.PROVENANCE_STYLE), fmt.text(run.model),
                                      fmt.text(run.provider), fmt.styled(run.status), fmt.clock(run.started_at)[:8], fmt.seconds(run.duration_seconds),
                                      f"{run.cases_attempted}/{run.case_count}", str(run.cases_failed), fmt.pct(run.pass_rate),
                                      f"{run.graded}/{run.cases_attempted}", fmt.text(fmt.truncate(fmt.cost(run.cost), 22)), fmt.ms(run.latency_ms_mean)]))
        sync_table(self.query_one("#runs-table", DataTable), rows)


class RunDetailView(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Panel("Run", id="run-meta")
        yield Panel("Progress", id="run-progress")
        yield Panel("Run events (latest 150)", id="run-events")
        with Horizontal(classes="buttons"):
            yield Input(placeholder="import attempts file (.json/.jsonl/.csv) into this run", id="import-path")
            yield Button("Import", id="btn-import")

    def show(self, state: ConsoleState) -> None:
        run = state.selected_run
        if run is None:
            self.query_one("#run-meta", Panel).update("No run selected. Pick one in the Runs tab (5) and press Enter.")
            self.query_one("#run-progress", Panel).update("")
            self.query_one("#run-events", Panel).update("")
            return
        params = ", ".join(f"{k}={v}" for k, v in sorted(run.parameters.items())) or fmt.NA
        budget = ", ".join(f"{k}={v}" for k, v in run.budget.items() if v is not None) or "unbounded"
        env = ", ".join(f"{k}={v}" for k, v in sorted(run.environment.items()))
        self.query_one("#run-meta", Panel).update(
            f"[b]{fmt.text(run.run_id)}[/]  {fmt.styled(run.provenance, fmt.PROVENANCE_STYLE)}  status {fmt.styled(run.status)}\n"
            f"model {fmt.text(run.model)}  provider {fmt.text(run.provider)}  suite {fmt.text(run.suite_version)}  mode {fmt.text(run.mode)}  seed {fmt.text(run.seed)}\n"
            f"generation {fmt.text(params)}\ncontext condition {fmt.text(run.context_condition)}  tools {fmt.NA}\n"
            f"budget {fmt.text(budget)}\nenvironment {fmt.text(env)}\n"
            f"started {fmt.text(run.started_at)}  finished {fmt.text(run.finished_at)}  duration {fmt.seconds(run.duration_seconds)}\n"
            f"storage {fmt.text(state.snapshot.db_path)}")
        self.query_one("#run-progress", Panel).update(
            f"{fmt.bar(run.cases_attempted, run.case_count, 40)}\n"
            f"attempts {run.attempts} (retries {run.retries})  failed cases {run.cases_failed}\n"
            f"grading: {run.graded} graded — {run.passed} passed, {run.failed_grades} failed, {run.abstained} needs review\n"
            f"cost {fmt.text(fmt.cost(run.cost))}  latency {fmt.ms(run.latency_ms_mean)} ({run.latency_known} measured)")
        self.query_one("#run-events", Panel).update("\n".join(event_line(e) for e in state.run_events[-40:]) or "[dim]no events for this run[/]")


class ResultsView(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Panel("Summary", id="results-summary")
        yield Static("[b]By domain[/]", markup=True)
        yield make_table("results-domain", BREAKDOWN_COLUMNS)
        yield Static("[b]By complexity[/]", markup=True)
        yield make_table("results-complexity", BREAKDOWN_COLUMNS)
        yield Static("[b]By split[/]", markup=True)
        yield make_table("results-split", BREAKDOWN_COLUMNS)

    def show(self, state: ConsoleState) -> None:
        run, results = state.selected_run, state.results
        if run is None or results is None:
            self.query_one("#results-summary", Panel).update("No run selected.")
            for table in ("#results-domain", "#results-complexity", "#results-split"):
                sync_table(self.query_one(table, DataTable), [])
            return
        statuses = ", ".join(f"{fmt.text(k)}={v}" for k, v in sorted(results.attempt_status_counts.items())) or fmt.NA
        self.query_one("#results-summary", Panel).update(
            f"run {fmt.text(run.run_id)} ({fmt.styled(run.provenance, fmt.PROVENANCE_STYLE)}) model {fmt.text(run.model)}\n"
            f"pass rate (decided cases) {fmt.pct(run.pass_rate)}  passed {run.passed}  failed {run.failed_grades}  needs review {run.abstained}  "
            f"ungraded {results.ungraded_attempts}\nattempt outcomes {statuses}  refusals/abstentions {results.refusals}\n"
            f"critical-failure assessment: {results.critical_unassessed} cases unassessed (deterministic graders do not assess critical failures)\n"
            f"{SPARSE_NOTE}")
        sync_table(self.query_one("#results-domain", DataTable), breakdown_rows(results.by_domain))
        sync_table(self.query_one("#results-complexity", DataTable), breakdown_rows(results.by_complexity))
        sync_table(self.query_one("#results-split", DataTable), breakdown_rows(results.by_split))


class CompareView(VerticalScroll):
    def compose(self) -> ComposeResult:
        with Horizontal(classes="buttons"):
            yield Select([], prompt="left run", id="cmp-left")
            yield Select([], prompt="right run", id="cmp-right")
            yield Button("Compare", id="btn-compare", variant="primary")
        yield make_table("cmp-dims", ("dimension", "left", "right", "note"))
        yield Static("[b]Quality by domain (matched cases)[/]", markup=True)
        yield make_table("cmp-domain", ("domain", "cases", "left scored", "right scored", "left score", "right score", "delta"))
        yield Panel("Limitations", id="cmp-limits")

    def set_run_options(self, state: ConsoleState) -> None:
        options = [(f"{r.run_id} · {r.model} · {r.provenance}", r.run_id) for r in state.snapshot.runs]
        signature = tuple(o[1] for o in options)
        if getattr(self, "_options", None) == signature:
            return
        self._options = signature
        for select_id in ("#cmp-left", "#cmp-right"):
            select = self.query_one(select_id, Select)
            value = select.value
            select.set_options(options)
            if value in signature:
                select.value = value

    def show(self, state: ConsoleState) -> None:
        self.set_run_options(state)
        comparison = state.comparison
        if comparison is None or state.comparison_runs is None:
            self.query_one("#cmp-limits", Panel).update("Pick two runs and press Compare. Only matched cases are compared; there is no leaderboard.")
            return
        runs = {r.run_id: r for r in state.snapshot.runs}
        left, right = (runs.get(run_id) for run_id in state.comparison_runs)

        def side(run: Any, getter: Any) -> str:
            return getter(run) if run is not None else fmt.NA

        dims = [
            ("evidence", side(left, lambda r: r.provenance), side(right, lambda r: r.provenance), "SIMULATED runs are not real-model evidence"),
            ("quality: mean grade score", fmt.pct(comparison.left_mean), fmt.pct(comparison.right_mean), f"{comparison.scored_pairs} scored pairs"),
            ("coverage: matched cases", str(comparison.matched_cases), str(comparison.matched_cases), f"families {len(comparison.family_counts)}"),
            ("failure rate (attempts)", side(left, lambda r: fmt.pct(r.cases_failed / r.cases_attempted if r.cases_attempted else None)),
             side(right, lambda r: fmt.pct(r.cases_failed / r.cases_attempted if r.cases_attempted else None)), ""),
            ("cost", side(left, lambda r: fmt.cost(r.cost)), side(right, lambda r: fmt.cost(r.cost)), ""),
            ("latency", side(left, lambda r: fmt.ms(r.latency_ms_mean)), side(right, lambda r: fmt.ms(r.latency_ms_mean)), ""),
            ("tool reliability", fmt.NOT_MEASURED, fmt.NOT_MEASURED, "no tool-use cases graded"),
            ("observed difference (left−right)", fmt.text(comparison.observed_difference), "",
             f"{comparison.uncertainty.get('method', 'uncertainty')} interval {comparison.uncertainty.get('interval')} "
             f"over {comparison.uncertainty.get('independent_families')} families" if isinstance(comparison.uncertainty, dict) else fmt.NA),
        ]
        sync_table(self.query_one("#cmp-dims", DataTable), [(d[0], [fmt.text(c) if i else c for i, c in enumerate(d)]) for d in dims])
        domain_rows = []
        for domain, stats in sorted(comparison.by_domain.items()):
            domain_rows.append((domain, [fmt.text(domain), fmt.text(stats.get("n")), fmt.text(stats.get("left_n")), fmt.text(stats.get("right_n")),
                                         fmt.text(stats.get("left_score")), fmt.text(stats.get("right_score")), fmt.text(stats.get("delta"))]))
        sync_table(self.query_one("#cmp-domain", DataTable), domain_rows)
        self.query_one("#cmp-limits", Panel).update("\n".join(f"• {fmt.text(item)}" for item in comparison.limitations) or "none reported")


class ReviewView(Vertical):
    def compose(self) -> ComposeResult:
        yield make_table("review-table", ("case", "model", "response", "grading", "critical", "review", "evidence", "reason"))
        yield Panel("Evidence", id="review-detail")

    def show(self, state: ConsoleState) -> None:
        items = state.results.review_items if state.results else []
        rows = [(item.case_id, [fmt.text(item.case_id), fmt.text(item.model), fmt.styled(item.response_status), fmt.styled(item.grading_status),
                                fmt.text(item.critical), fmt.text(item.review_status), fmt.styled(item.provenance, fmt.PROVENANCE_STYLE),
                                fmt.text(fmt.truncate(item.reason, 60))]) for item in items]
        sync_table(self.query_one("#review-table", DataTable), rows)
        if not items:
            self.query_one("#review-detail", Panel).update("Nothing needs review for the selected run." if state.results else "No run selected.")

    def show_item(self, state: ConsoleState, case_id: str) -> None:
        item = next((i for i in (state.results.review_items if state.results else []) if i.case_id == case_id), None)
        if item is None:
            return
        self.query_one("#review-detail", Panel).update(
            f"[b]{fmt.text(item.case_id)}[/] run {fmt.text(item.run_id)} attempt {fmt.text(item.attempt_id)}\n"
            f"response status {fmt.styled(item.response_status)}  grading {fmt.styled(item.grading_status)}  critical {fmt.text(item.critical)}  "
            f"review {fmt.text(item.review_status)}  evidence {fmt.styled(item.provenance, fmt.PROVENANCE_STYLE)}\n"
            f"reason {fmt.text(item.reason)}\nerror {fmt.text(item.error)}\n"
            f"[dim]candidate response:[/] {fmt.text(item.response_excerpt, '(empty)')}\n"
            "[dim]Blind human review: `model-lab review export/import` (labels are bound to attempts).[/]")


class RoutingView(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Panel("Routing evidence", id="routing-summary")
        yield make_table("routing-table", ("candidate", "label", "observed quality", "eligible", "coverage", "expected cost", "expected latency"))
        yield Panel("Constraints and warnings", id="routing-limits")

    def show(self, state: ConsoleState) -> None:
        if not state.routing:
            self.query_one("#routing-summary", Panel).update(
                "No routing evidence yet. Compare two runs (tab 8) to produce [cyan]PROPOSED[/] draft recommendations.\n"
                "Labels: [green]MEASURED[/] live provider · [magenta]SIMULATED[/] fake provider · [cyan]IMPORTED[/] ingested · [cyan]PROPOSED[/] draft routing.\n"
                "The console never writes production router configuration.")
            sync_table(self.query_one("#routing-table", DataTable), [])
            self.query_one("#routing-limits", Panel).update("")
            return
        left, right = state.comparison_runs or ("?", "?")
        self.query_one("#routing-summary", Panel).update(
            f"[cyan]PROPOSED[/] draft-only recommendations from comparison {fmt.text(left)} vs {fmt.text(right)}. "
            "Simulated outcomes only when evidence is SIMULATED. Budget: expected cost/latency are unknown until measured.")
        rows = []
        for rec in state.routing:
            label = "SIMULATED" if rec.get("synthetic") else "PROPOSED"
            rows.append((rec["recommendation_id"], [fmt.text(rec["candidate_model"]), fmt.styled(label, fmt.PROVENANCE_STYLE), fmt.pct(rec.get("observed_quality")),
                                                   "[green]yes[/]" if rec.get("eligibility") else "[red]no[/]", fmt.text(rec.get("coverage")),
                                                   fmt.text(rec.get("expected_cost"), fmt.NOT_MEASURED), fmt.text(rec.get("expected_latency_ms"), fmt.NOT_MEASURED)]))
        sync_table(self.query_one("#routing-table", DataTable), rows)
        warnings = []
        for rec in state.routing:
            warnings.append(f"[b]{fmt.text(rec['candidate_model'])}[/]")
            warnings.extend(f"  • {fmt.text(item)}" for item in rec.get("limitations", []))
        self.query_one("#routing-limits", Panel).update("\n".join(warnings))
