"""Untrusted telemetry and gate reasons must remain data in exported reports."""

import json

from model_lab.application.optimization_report import render_html, render_markdown, write


def test_optimization_report_escapes_untrusted_evidence_and_gate_reasons(tmp_path):
    attack = "`</code><script>alert(1)</script>|\n## forged decision"
    report = {
        "policy_candidate_id": attack,
        "report_id": attack,
        "evidence_class": attack,
        "dataset_id": attack,
        "passed": False,
        "failed_gates": [attack],
        "hard_gates": [{"gate": attack, "passed": False, "reason": attack}],
        "limitations": [attack],
        "core_regression": {},
        "ope": {"validation": {"warnings": [attack]}},
    }
    rendered_html = render_html(report, {"source": attack})
    rendered_md = render_markdown(report, {"source": attack})
    assert "<script>" not in rendered_html
    assert "&lt;script&gt;" in rendered_html
    assert "\n## forged decision" not in rendered_md
    assert "&#96;" in rendered_md
    assert "`</code>" not in rendered_md
    assert "<script>" not in rendered_md
    assert rendered_md.count("## Decision") == 1
    assert rendered_md.count("## Evidence") == 1
    assert rendered_md.count("## Analysis") == 1
    files = write(report, tmp_path, {"source": attack})
    assert json.loads(files["json"].read_text())["decision"]["failed_gates"] == [attack]
    assert files["md"].read_text() == rendered_md
    assert files["html"].read_text() == rendered_html
