"""Small dependency-free command-line entry point; deeper commands are added by modules."""

from __future__ import annotations

import argparse
import json
import sys

from .benchmark import export_candidate_jsonl, load_suite, validate_suite
from .errors import ModelLabError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model-lab", description="Offline-first reproducible model evaluation laboratory")
    sub = parser.add_subparsers(dest="command", required=True)
    suite = sub.add_parser("suite", help="validate, inspect, or export a benchmark suite")
    suite_sub = suite.add_subparsers(dest="suite_command", required=True)
    validate = suite_sub.add_parser("validate")
    validate.add_argument("path")
    inspect = suite_sub.add_parser("inspect")
    inspect.add_argument("path")
    export = suite_sub.add_parser("export")
    export.add_argument("path")
    export.add_argument("--out", required=True)
    export.add_argument("--candidate-only", action="store_true", default=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "suite":
            suite = load_suite(args.path)
            if args.suite_command in {"validate", "inspect"}:
                print(json.dumps(validate_suite(suite), indent=2, sort_keys=True))
            elif args.suite_command == "export":
                if not args.candidate_only:
                    raise ModelLabError("only --candidate-only export is supported for protected seed suites")
                count = export_candidate_jsonl(suite, args.out)
                print(json.dumps({"exported": count, "path": args.out, "candidate_only": True}, sort_keys=True))
            return 0
    except ModelLabError as exc:
        print(f"model-lab: error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

