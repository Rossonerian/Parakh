import json
from pathlib import Path

from model_lab.cli import main
from model_lab.pipeline import run_offline_demo


ROOT = Path(__file__).parents[1]


def test_operational_cli_surface(tmp_path: Path):
    workspace = tmp_path / "workspace"
    assert main(["init", str(workspace)]) == 0
    assert (workspace / "model-lab.json").is_file()

    plan_path = tmp_path / "plan.json"
    assert main(["plan", "--suite", str(ROOT / "benchmarks/seed_cases.jsonl"), "--models", "synthetic-good,synthetic-incorrect", "--repeats", "2", "--out", str(plan_path)]) == 0
    assert json.loads(plan_path.read_text())["maximum_requests"] == 240

    demo_dir = tmp_path / "demo"
    run_offline_demo(ROOT / "benchmarks/seed_cases.jsonl", demo_dir, seed=41)
    comparison_path = tmp_path / "comparison.json"
    assert main(["compare", "--db", str(demo_dir / "model_lab.sqlite3"), "--suite", str(ROOT / "benchmarks/seed_cases.jsonl"), "--left-run", "run-synthetic-good", "--right-run", "run-synthetic-incorrect", "--out", str(comparison_path)]) == 0
    assert json.loads(comparison_path.read_text())["observed_difference"] == 1.0

    report_dir = tmp_path / "report"
    assert main(["report", "--db", str(demo_dir / "model_lab.sqlite3"), "--suite", str(ROOT / "benchmarks/seed_cases.jsonl"), "--run", "run-synthetic-good", "--out", str(report_dir)]) == 0
    assert (report_dir / "report.html").is_file()
    assert main(["audit", "--db", str(demo_dir / "model_lab.sqlite3"), "--run", "run-synthetic-good"]) == 0

    manifest_path = tmp_path / "manifest.json"
    assert main(["promptfoo", "export", "--suite", str(ROOT / "benchmarks/seed_cases.jsonl"), "--out", str(manifest_path)]) == 0
    manifest = json.loads(manifest_path.read_text())
    assert manifest["artifact_type"] == "model_lab.promptfoo_manifest"


def test_cli_subcommand_help_descriptions():
    from model_lab.cli import build_parser

    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0].choices

    init_help = subparsers["init"].format_help()
    assert "workspace directory path" in init_help

    run_help = subparsers["run"].format_help()
    assert "path to benchmark suite file" in run_help
    assert "output directory for run artifacts" in run_help

    demo_help = subparsers["demo"].format_help()
    assert "random seed for demo evaluation" in demo_help
