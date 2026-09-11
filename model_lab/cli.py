"""Dependency-free command line interface for the ModelLab."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from .benchmark import export_candidate_jsonl, load_suite, validate_suite
from .analysis import compare_grades
from .errors import IntegrityError, ModelLabError
from .grading import grade_attempt
from .ingestion import ingest_file
from .pipeline import run_offline_demo
from .promptfoo import export_promptfoo_manifest, import_promptfoo_fixture
from .reporting import write_report_bundle
from .review import export_blind_review, import_blind_reviews
from .schemas import Budget, ModelConfig, Run, utc_now
from .storage import SQLiteStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model-lab", description="Offline-first reproducible model evaluation laboratory")
    sub = parser.add_subparsers(dest="command", required=True)

    suite = sub.add_parser("suite", help="validate, inspect, or export a benchmark suite")
    suite_sub = suite.add_subparsers(dest="suite_command", required=True)
    for name in ("validate", "inspect"):
        command = suite_sub.add_parser(name)
        command.add_argument("path")
    export = suite_sub.add_parser("export")
    export.add_argument("path")
    export.add_argument("--out", required=True)
    export.add_argument("--candidate-only", action="store_true", default=False)

    demo = sub.add_parser("demo", help="run the complete 60-case offline fake-provider workflow")
    demo.add_argument("--suite", default="benchmarks/seed_cases.jsonl")
    demo.add_argument("--out", default="lab-data/demo")
    demo.add_argument("--seed", type=int, default=7)

    doctor = sub.add_parser("doctor", help="check local offline prerequisites")
    doctor.add_argument("--suite", default="benchmarks/seed_cases.jsonl")

    init = sub.add_parser("init", help="create a local ModelLab workspace")
    init.add_argument("path", default="lab-data", nargs="?")

    plan = sub.add_parser("plan", help="write a bounded experiment plan without executing it")
    plan.add_argument("--suite", default="benchmarks/seed_cases.jsonl")
    plan.add_argument("--models", required=True, help="comma-separated provider/model labels")
    plan.add_argument("--repeats", type=int, default=1)
    plan.add_argument("--out", required=True)
    plan.add_argument("--budget-usd", type=float)

    run = sub.add_parser("run", help="run one offline fake-provider experiment")
    run.add_argument("--suite", default="benchmarks/seed_cases.jsonl")
    run.add_argument("--out", default="lab-data/run")
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--model", default="synthetic-v1")
    run.add_argument("--max-cases", type=int)

    imported = sub.add_parser("import", help="import structured attempts into an existing SQLite run")
    imported.add_argument("path")
    imported.add_argument("--db", required=True)
    imported.add_argument("--run", required=True, dest="run_id")
    imported.add_argument("--format", choices=("jsonl", "json", "csv"))
    imported.add_argument("--source-label", default="cli-import")

    for name in ("grade", "compare", "report", "audit"):
        command = sub.add_parser(name, help=f"{name} an existing offline experiment")
        command.add_argument("--summary", required=False)
        command.add_argument("--run", required=False, dest="run_id")
        if name in {"grade", "compare", "report", "audit"}:
            command.add_argument("--db")
            command.add_argument("--suite")
        if name == "compare":
            command.add_argument("--left-run")
            command.add_argument("--right-run")
            command.add_argument("--out")
        if name == "report":
            command.add_argument("--out")
        if name == "audit":
            command.add_argument("--out")

    promptfoo = sub.add_parser("promptfoo", help="export/import versioned Promptfoo-shaped fixtures")
    promptfoo_sub = promptfoo.add_subparsers(dest="promptfoo_command", required=True)
    promptfoo_export = promptfoo_sub.add_parser("export")
    promptfoo_export.add_argument("--suite", default="benchmarks/seed_cases.jsonl")
    promptfoo_export.add_argument("--out", required=True)
    promptfoo_export.add_argument("--run-id", default="promptfoo-run")
    promptfoo_import = promptfoo_sub.add_parser("import")
    promptfoo_import.add_argument("--manifest", required=True)
    promptfoo_import.add_argument("--artifact", required=True)
    promptfoo_import.add_argument("--quarantine-dir")

    review = sub.add_parser("review", help="export or import blind human review records")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_export = review_sub.add_parser("export")
    review_export.add_argument("--db", required=True)
    review_export.add_argument("--run", required=True, dest="run_id")
    review_export.add_argument("--out", required=True)
    review_export.add_argument("--include-prompt", action="store_true")
    review_import = review_sub.add_parser("import")
    review_import.add_argument("--db", required=True)
    review_import.add_argument("--run", required=True, dest="run_id")
    review_import.add_argument("--in", required=True, dest="input_path")

    router = sub.add_parser("router", help="produce draft routing evidence")
    router_sub = router.add_subparsers(dest="router_command", required=True)
    recommend = router_sub.add_parser("recommend")
    recommend.add_argument("--summary", default="lab-data/demo/summary.json")
    recommend.add_argument("--out")
    recommend.add_argument("--draft", action="store_true", default=False)
    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _run_rows(suite: object, store: SQLiteStore, run_id: str) -> tuple[list[object], list[object], list[dict[str, object]]]:
    attempts = store.list_attempts(run_id)
    cases = {case.case_id: case for case in suite.cases}
    grades = [grade_attempt(cases[attempt.case_id], attempt) for attempt in attempts]
    grades_by_attempt = {grade.attempt_id: grade for grade in grades}
    rows = []
    for attempt in attempts:
        case = cases[attempt.case_id]
        grade = grades_by_attempt[attempt.attempt_id]
        rows.append({
            "attempt_id": attempt.attempt_id, "case_id": attempt.case_id,
            "provider": attempt.model_config.provider, "model": attempt.model_config.model,
            "domain": case.domain, "workflow": case.family_id,
            "complexity_level": case.complexity_level, "split": case.split,
            "passed": grade.passed, "score": grade.score,
            "latency_ms": attempt.completion_latency_ms, "cost_minor": attempt.cost_minor,
            "response_text": attempt.response_text, "status": attempt.status.value,
            "prompt_hash": attempt.prompt_hash, "synthetic": attempt.raw_metadata.get("synthetic", False),
        })
    return attempts, grades, rows


def _write_json(path: str | Path, value: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "suite":
            suite = load_suite(args.path)
            if args.suite_command in {"validate", "inspect"}:
                _print_json(validate_suite(suite))
            elif args.suite_command == "export":
                if not args.candidate_only:
                    raise ModelLabError("only --candidate-only export is supported for protected seed suites")
                count = export_candidate_jsonl(suite, args.out)
                _print_json({"exported": count, "path": args.out, "candidate_only": True})
            return 0
        if args.command == "demo":
            _print_json(run_offline_demo(args.suite, args.out, seed=args.seed))
            return 0
        if args.command == "doctor":
            suite_path = Path(args.suite)
            checks = {"python_3_12_plus": sys.version_info >= (3, 12), "benchmark_present": suite_path.is_file()}
            if checks["benchmark_present"]:
                checks["benchmark_cases"] = validate_suite(load_suite(suite_path))["cases"]
            checks["offline_ready"] = all(value is True for key, value in checks.items() if key != "benchmark_cases") and checks.get("benchmark_cases") == 60
            _print_json(checks)
            return 0 if checks["offline_ready"] else 2
        if args.command == "init":
            destination = Path(args.path)
            destination.mkdir(parents=True, exist_ok=True)
            config = {"version": 1, "data_dir": str(destination), "provider_mode": "offline_fake_default", "secrets_from_environment": True}
            _write_json(destination / "model-lab.json", config)
            _print_json({"initialized": True, "path": str(destination), "config": str(destination / "model-lab.json")})
            return 0
        if args.command == "plan":
            suite = load_suite(args.suite)
            if args.repeats < 1:
                raise ModelLabError("--repeats must be positive")
            models = tuple(model.strip() for model in args.models.split(",") if model.strip())
            if not models:
                raise ModelLabError("--models must contain at least one model")
            cases = len(suite.cases)
            plan = {"plan_version": 1, "suite_version": suite.suite_version, "suite_hash": suite.source_hash, "models": list(models), "cases": cases, "repeats": args.repeats, "maximum_requests": cases * args.repeats * len(models), "budget_usd": args.budget_usd, "paid_execution_allowed": False, "synthetic_default": True}
            _write_json(args.out, plan)
            _print_json(plan)
            return 0
        if args.command == "run":
            suite = load_suite(args.suite)
            from .execution import ExecutionEngine
            from .providers.fake import FakeProvider
            store = SQLiteStore(Path(args.out) / "model_lab.sqlite3")
            try:
                case_ids = suite.case_ids[:args.max_cases] if args.max_cases else suite.case_ids
                run = Run(run_id="run-cli", suite_version=suite.suite_version, case_ids=case_ids, model_config=ModelConfig(provider="fake", model=args.model, parameters={"temperature": 0, "synthetic": True}), seed=args.seed, budget=Budget(max_cases=len(case_ids), max_requests=len(case_ids)), started_at=utc_now(), environment={"mode": "offline_synthetic"})
                result = ExecutionEngine(store, FakeProvider(model=args.model)).execute(suite, run, case_ids=case_ids)
                _print_json({"run_id": result.run_id, "status": result.status, "attempts": len(result.attempts), "failures": result.failures, "synthetic": True})
            finally:
                store.close()
            return 0
        if args.command == "import":
            store = SQLiteStore(args.db)
            try:
                result = ingest_file(store, args.run_id, args.path, fmt=args.format, source_label=args.source_label)
                _print_json({"imported": result.imported, "quarantined": result.quarantined, "duplicates": result.duplicates})
            finally:
                store.close()
            return 0
        if args.command == "promptfoo":
            if args.promptfoo_command == "export":
                suite = load_suite(args.suite)
                manifest = export_promptfoo_manifest([case.candidate_payload() for case in suite.cases], run_id=args.run_id)
                _write_json(args.out, manifest)
                _print_json({"exported": len(suite.cases), "path": args.out, "candidate_only": True, "manifest_hash": manifest["manifest_hash"]})
            else:
                manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
                result = import_promptfoo_fixture(args.artifact, manifest, quarantine_dir=args.quarantine_dir)
                _print_json({"accepted": result.accepted, "attempts": len(result.attempts), "errors": list(result.errors), "source_hash": result.source_hash, "quarantine_path": str(result.quarantine_path) if result.quarantine_path else None})
                return 0 if result.accepted else 2
            return 0
        if args.command == "review":
            store = SQLiteStore(args.db)
            try:
                if args.review_command == "export":
                    records = export_blind_review(store.list_attempts(args.run_id), include_prompt=args.include_prompt)
                    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                    Path(args.out).write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
                    _print_json({"exported": len(records), "path": args.out, "blind": True})
                else:
                    records = [json.loads(line) for line in Path(args.input_path).read_text(encoding="utf-8").splitlines() if line.strip()]
                    reviews = [replace(review, run_id=args.run_id) for review in import_blind_reviews(records)]
                    for review in reviews:
                        store.add_review(review)
                    _print_json({"imported": len(reviews), "run_id": args.run_id, "blind": True})
            finally:
                store.close()
            return 0
        if args.command == "router" and args.router_command == "recommend":
            if not args.draft:
                raise ModelLabError("routing recommendations require explicit --draft acknowledgement")
            source = Path(args.summary)
            value = json.loads(source.read_text(encoding="utf-8"))
            recommendations = value.get("routing_recommendations", [])
            if args.out:
                Path(args.out).write_text(json.dumps(recommendations, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            _print_json({"draft": True, "recommendations": recommendations, "production_config_changed": False})
            return 0
        if args.command in {"grade", "compare", "report", "audit"}:
            if args.command == "grade" and args.db and args.suite and args.run_id:
                suite = load_suite(args.suite)
                store = SQLiteStore(args.db)
                added = abstained = 0
                try:
                    for attempt in store.list_attempts(args.run_id):
                        grade = grade_attempt(suite.get(attempt.case_id), attempt)
                        try:
                            store.add_grade(grade)
                            added += 1
                        except IntegrityError:
                            abstained += 1
                finally:
                    store.close()
                _print_json({"graded": added, "already_present": abstained, "run_id": args.run_id})
                return 0
            if args.db and ((args.command == "compare" and args.left_run and args.right_run) or (args.command in {"report", "audit"} and args.run_id)):
                store = SQLiteStore(args.db)
                try:
                    if args.command == "audit":
                        run = store.get_run(args.run_id)
                        audit = {"run_id": args.run_id, "status": run.status, "attempts": store.count("attempts", args.run_id), "grades": store.count("grades", args.run_id), "reviews": store.count("reviews", args.run_id), "quarantined": len(store.quarantined()), "synthetic": run.environment.get("mode") == "offline_synthetic"}
                        if args.out:
                            _write_json(args.out, audit)
                        _print_json(audit)
                        return 0
                    if not args.suite:
                        raise ModelLabError(f"{args.command} with --db requires --suite")
                    suite = load_suite(args.suite)
                    if args.command == "report":
                        _, _, rows = _run_rows(suite, store, args.run_id)
                        output = args.out or "reports"
                        artifacts = write_report_bundle(rows, output, metadata={"run_id": args.run_id, "suite_version": suite.suite_version, "suite_hash": suite.source_hash})
                        _print_json({"run_id": args.run_id, "artifacts": {key: str(value) for key, value in artifacts.items()}})
                        return 0
                    if not args.left_run or not args.right_run:
                        raise ModelLabError("compare with --db requires --left-run and --right-run")
                    _, left_grades, _ = _run_rows(suite, store, args.left_run)
                    _, right_grades, _ = _run_rows(suite, store, args.right_run)
                    comparison = compare_grades(left_grades, right_grades, cases=suite.cases)
                    value = comparison.to_dict()
                    if args.out:
                        _write_json(args.out, value)
                    _print_json(value)
                    return 0
                finally:
                    store.close()
            if not args.summary:
                raise ModelLabError(f"{args.command} requires --summary for the offline workflow")
            value = json.loads(Path(args.summary).read_text(encoding="utf-8"))
            _print_json({"command": args.command, "summary": value, "synthetic": True})
            return 0
    except (ModelLabError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"model-lab: error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
