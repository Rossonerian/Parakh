from __future__ import annotations

import json
from pathlib import Path

import pytest

from model_lab.promptfoo import (
    PromptfooImportError,
    export_promptfoo_manifest,
    import_promptfoo_fixture,
    invoke_promptfoo,
)
from model_lab.reporting import (
    build_report,
    render_csv,
    render_html,
    render_json,
    render_markdown,
    write_report_bundle,
)


def _attempts() -> list[dict[str, object]]:
    return [
        {
            "attempt_id": "a-1",
            "case_id": "case-1",
            "model": "fake-good",
            "provider": "fake",
            "domain": "calendar",
            "workflow": "calendar-workflow-family-v1",
            "complexity_level": 1,
            "split": "train",
            "passed": True,
            "score": 1.0,
            "latency_ms": 12.0,
            "cost_minor": None,
            "response_text": "<safe & useful>",
            "status": "success",
            "prompt_hash": "p-1",
        },
        {
            "attempt_id": "a-2",
            "case_id": "case-2",
            "model": "fake-good",
            "provider": "fake",
            "domain": "calendar",
            "workflow": "calendar-workflow-family-v1",
            "complexity_level": 2,
            "split": "holdout",
            "passed": None,
            "score": None,
            "latency_ms": None,
            "cost_minor": None,
            "response_text": "unknown",
            "status": "timeout",
            "prompt_hash": "p-2",
        },
    ]


def _candidate_cases() -> list[dict[str, object]]:
    return [
        {
            "case_id": "case-1",
            "messages": [{"role": "user", "content": "Say hello"}],
            "limits": {"max_output_tokens": 10, "max_tool_calls": 0},
            "prompt_hash": "abc123",
        }
    ]


def test_report_formats_are_deterministic_and_preserve_unknowns() -> None:
    report = build_report(
        _attempts(),
        metadata={"run_id": "run-1", "suite_version": "0.1.0", "synthetic": True},
    )

    assert report["summary"]["quality"]["known_count"] == 1
    assert report["summary"]["quality"]["unknown_count"] == 1
    assert report["summary"]["latency_ms"]["known_count"] == 1
    assert report["summary"]["cost_minor"]["known_count"] == 0
    rendered = render_json(report)
    assert rendered == render_json(report)
    assert "unknown" in render_markdown(report).lower()


def test_csv_formula_cells_are_escaped_and_html_is_safe() -> None:
    attempts = _attempts() + [
        {
            **_attempts()[0],
            "attempt_id": "a-3",
            "case_id": "case-3",
            "response_text": "=HYPERLINK(\"https://evil.example\")",
        }
    ]
    report = build_report(attempts)
    csv_text = render_csv(report)
    html = render_html(report)

    assert "'=HYPERLINK" in csv_text
    assert "&lt;safe &amp; useful&gt;" in html
    assert "<script" not in html.lower()
    assert "&lt;" in html


def test_report_bundle_writes_json_markdown_csv_html_and_charts(tmp_path: Path) -> None:
    artifacts = write_report_bundle(_attempts(), tmp_path, metadata={"run_id": "run-1"})

    assert {path.suffix for path in artifacts.values() if path.is_file()} >= {".json", ".csv", ".md", ".html"}
    chart = tmp_path / "quality_by_model.svg"
    assert chart.is_file()
    assert "<svg" in chart.read_text(encoding="utf-8")
    # PNG is optional; if unavailable, the bundle must say so rather than fake bytes.
    if "quality_by_model_png" in artifacts:
        assert artifacts["quality_by_model_png"].read_bytes().startswith(b"\x89PNG")
    else:
        assert "PNG chart skipped" in (tmp_path / "charts.json").read_text(encoding="utf-8")


def test_promptfoo_manifest_is_candidate_only_and_hashed() -> None:
    manifest = export_promptfoo_manifest(_candidate_cases(), run_id="run-1")
    serialized = json.dumps(manifest, sort_keys=True)

    assert manifest["artifact_type"] == "model_lab.promptfoo_manifest"
    assert manifest["artifact_version"] == 1
    assert manifest["manifest_hash"]
    for forbidden in ("reference_answer", "evaluation", "rubric", "split", "domain", "family_id"):
        assert forbidden not in serialized
    assert manifest["tests"][0]["metadata"] == {"case_id": "case-1", "prompt_hash": "abc123"}


def test_promptfoo_fixture_import_accepts_and_quarantines_tampering(tmp_path: Path) -> None:
    manifest = export_promptfoo_manifest(_candidate_cases(), run_id="run-1")
    fixture = {
        "artifact_type": "model_lab.promptfoo_result",
        "artifact_version": 1,
        "manifest_hash": manifest["manifest_hash"],
        "results": [{"case_id": "case-1", "prompt_hash": "abc123", "output": "hello", "status": "success"}],
    }
    accepted = import_promptfoo_fixture(fixture, manifest)
    assert accepted.accepted is True
    assert accepted.attempts[0]["response_text"] == "hello"

    tampered = {**fixture, "results": [{**fixture["results"][0], "prompt_hash": "changed"}]}
    quarantined = import_promptfoo_fixture(tampered, manifest, quarantine_dir=tmp_path)
    assert quarantined.accepted is False
    assert quarantined.quarantine_path is not None
    assert quarantined.errors
    assert quarantined.quarantine_path.is_file()


def test_promptfoo_import_rejects_duplicate_and_unknown_case_ids() -> None:
    manifest = export_promptfoo_manifest(_candidate_cases(), run_id="run-1")
    fixture = {
        "artifact_type": "model_lab.promptfoo_result",
        "artifact_version": 1,
        "manifest_hash": manifest["manifest_hash"],
        "results": [
            {"case_id": "case-1", "prompt_hash": "abc123", "output": "one"},
            {"case_id": "case-1", "prompt_hash": "abc123", "output": "two"},
            {"case_id": "unknown", "prompt_hash": "x", "output": "three"},
        ],
    }
    result = import_promptfoo_fixture(fixture, manifest)
    assert result.accepted is False
    assert any("duplicate case ID" in error for error in result.errors)
    assert any("unknown case ID" in error for error in result.errors)


def test_promptfoo_live_invocation_fails_closed() -> None:
    manifest = export_promptfoo_manifest(_candidate_cases(), run_id="run-1")

    with pytest.raises(PromptfooImportError, match="approved"):
        invoke_promptfoo(manifest)
    with pytest.raises(PromptfooImportError, match="runner"):
        invoke_promptfoo(manifest, approved_plan=True)
