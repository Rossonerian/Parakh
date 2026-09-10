import json
from pathlib import Path

from model_lab.pipeline import run_offline_demo


ROOT = Path(__file__).parents[1]


def test_complete_60_case_offline_pipeline(tmp_path: Path):
    first = run_offline_demo(ROOT / "benchmarks/seed_cases.jsonl", tmp_path / "first", seed=11)
    second = run_offline_demo(ROOT / "benchmarks/seed_cases.jsonl", tmp_path / "second", seed=11)

    assert first["cases"] == 60
    assert first["runs"]["synthetic-good"]["attempts"] == 60
    assert first["runs"]["synthetic-incorrect"]["attempts"] == 60
    assert first["runs"]["synthetic-good"]["status"] == "completed"
    assert first["runs"]["synthetic-incorrect"]["status"] == "completed"
    assert first["runs"]["synthetic-good"]["digest"] == second["runs"]["synthetic-good"]["digest"]
    assert first["runs"]["synthetic-incorrect"]["digest"] == second["runs"]["synthetic-incorrect"]["digest"]
    assert first["comparison"]["matched_cases"] == 60
    assert first["routing_recommendations"][0]["candidate_model"] == "synthetic-good"
    assert first["promptfoo"]["accepted_fixture"] is True
    assert first["promptfoo"]["tampered_fixture_accepted"] is False
    assert Path(first["promptfoo"]["quarantine_path"]).is_file()
    assert (tmp_path / "first/reports/synthetic-good/report.html").is_file()
    manifest = json.loads((tmp_path / "first/promptfoo-manifest.json").read_text(encoding="utf-8"))
    serialized = json.dumps(manifest, sort_keys=True)
    assert "reference_answer" not in serialized
    assert '"split"' not in serialized
