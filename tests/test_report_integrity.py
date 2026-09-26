import json

import pytest

from model_lab.application.reporting import build_report, render_csv, render_html, render_markdown


def test_report_rejects_nonfinite_and_mixed_currency_keeps_total_unknown():
    with pytest.raises(ValueError):
        build_report([{"attempt_id": "a", "latency_ms": float("nan")}])
    report = build_report([
        {"attempt_id": "a", "cost_minor": 5, "currency": "USD", "score": 1, "critical_assessment": "assessed"},
        {"attempt_id": "b", "cost_minor": 7, "currency": "EUR", "score": 0, "critical_assessment": "assessed"},
    ])
    assert report["summary"]["cost_minor"]["observed_subtotal_minor"] == 12
    assert report["summary"]["cost_minor"]["total_minor"] is None
    assert report["summary"]["cost_per_verified_success"] is None


def test_report_formula_safe_markdown_html_and_context_critical_unknowns():
    report = build_report([{"attempt_id": "=bad", "case_id": "c|x", "model": "<script>", "score": None,
                            "latency_ms": 10, "context_condition": "short", "critical_assessment": "unassessed"}])
    assert "'=bad" in render_csv(report)
    assert "<script>" not in render_html(report)
    assert "By context condition" in render_markdown(report)
    assert report["summary"]["coverage"]["critical_assessed"] == 0


def test_direct_attempt_normalizes_model_and_latency():
    from model_lab.schemas import Attempt, AttemptStatus, ModelConfig, utc_now
    attempt = Attempt(attempt_id="a", run_id="r", logical_request_id="l", case_id="c",
                      model_config=ModelConfig(provider="p", model="m", context_condition="long"),
                      prompt_hash="x" * 16, response_text="ok", status=AttemptStatus.SUCCESS,
                      started_at=utc_now(), completion_latency_ms=12)
    report = build_report([attempt])
    row = report["rows"][0]
    assert row["model"] == "m" and row["latency_ms"] == 12 and row["context_condition"] == "long"

