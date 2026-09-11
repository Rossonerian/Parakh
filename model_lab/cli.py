"""Dependency-free command line interface for the ModelLab."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from .benchmark import export_candidate_jsonl, load_suite, validate_suite
from .errors import IntegrityError, ModelLabError
from .grading import grade_attempt
from .ingestion import ingest_file
from .pipeline import run_offline_demo
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
        if name == "grade":
            command.add_argument("--db")
            command.add_argument("--suite")

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
