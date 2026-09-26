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
    cost = report["summary"]["cost_minor"]
    assert cost["observed_subtotal_minor"] is None
    assert cost["currency_consistent"] is False
    assert cost["complete"] is False
    assert cost["total_minor"] is None
    assert report["summary"]["cost_per_verified_success"] is None


def test_acceptance_a_mixed_currency_and_missing_currency():
    # Defect A: Rows USD 1200 + INR 500 -> observed_subtotal_minor is None, currency_consistent False, complete False
    report_mixed = build_report([
        {"attempt_id": "a-1", "cost_minor": 1200, "currency": "USD"},
        {"attempt_id": "a-2", "cost_minor": 500, "currency": "INR"},
    ])
    cost_mixed = report_mixed["summary"]["cost_minor"]
    assert cost_mixed["observed_subtotal_minor"] is None
    assert cost_mixed["currency_consistent"] is False
    assert cost_mixed["complete"] is False
    assert cost_mixed["total_minor"] is None

    # Missing currency when cost is known also makes currency inconsistent
    report_missing = build_report([
        {"attempt_id": "a-3", "cost_minor": 500, "currency": None},
    ])
    cost_missing = report_missing["summary"]["cost_minor"]
    assert cost_missing["observed_subtotal_minor"] is None
    assert cost_missing["currency_consistent"] is False
    assert cost_missing["complete"] is False


def test_acceptance_b_verified_success_and_cost_per_verified_success():
    # Defect B: Two USD rows (1200 passed, 500 failed; both critical_assessment assessed)
    # Expected: cost_per_verified_success == 1700
    rows = [
        {"attempt_id": "b-1", "cost_minor": 1200, "currency": "USD", "passed": True, "score": 1.0, "critical_assessment": "assessed"},
        {"attempt_id": "b-2", "cost_minor": 500, "currency": "USD", "passed": False, "score": 0.0, "critical_assessment": "assessed"},
    ]
    report = build_report(rows)
    assert report["summary"]["verified_success_count"] == 1
    assert report["summary"]["cost_per_verified_success"] == 1700

    # If critical_assessment is unassessed or None, row is not a verified success
    rows_unassessed = [
        {"attempt_id": "b-3", "cost_minor": 1200, "currency": "USD", "passed": True, "critical_assessment": "unassessed"},
        {"attempt_id": "b-4", "cost_minor": 500, "currency": "USD", "passed": True, "critical_assessment": None},
    ]
    report_unassessed = build_report(rows_unassessed)
    assert report_unassessed["summary"]["verified_success_count"] == 0
    assert report_unassessed["summary"]["cost_per_verified_success"] is None


def test_acceptance_c_markdown_label_escaping():
    # Defect C: Model label "x\n# Injected heading\n<img src=x onerror=alert(1)>"
    # Acceptance: no rendered Markdown line starts with '# Injected' and no raw '<img' substring.
    rows = [
        {
            "attempt_id": "c-1",
            "model": "x\n# Injected heading\n<img src=x onerror=alert(1)>",
            "context_condition": "cond\n# Injected sub\n<img src=y>",
            "score": 0.8,
            "passed": True,
            "critical_assessment": "assessed",
        }
    ]
    report = build_report(rows)
    md = render_markdown(report)
    for line in md.splitlines():
        assert not line.strip().startswith("# Injected"), f"Rendered line starts with '# Injected': {line}"
    assert "<img" not in md, f"Raw <img found in rendered markdown: {md}"


def test_acceptance_d_svg_views_safety_and_unknown_placeholders():
    # Defect D: model/domain quality SVG view, cost-versus-verified-success view, and context view.
    # Acceptance: render_html contains '<svg' for each view, no '<script', no 'http://' or 'https://' in src/href,
    # and shows a placeholder when cost is unknown.

    report_unknown_cost = build_report([
        {
            "attempt_id": "d-1",
            "model": "model-a",
            "domain": "finance",
            "context_condition": "standard",
            "score": 0.85,
            "passed": True,
            "critical_assessment": "assessed",
        }
    ])
    html_unknown = render_html(report_unknown_cost)
    assert html_unknown.count("<svg") >= 3
    assert "<script" not in html_unknown.lower()
    assert 'src="http://' not in html_unknown and "src='http://" not in html_unknown
    assert 'src="https://' not in html_unknown and "src='https://" not in html_unknown
    assert 'href="http://' not in html_unknown and "href='http://" not in html_unknown
    assert 'href="https://' not in html_unknown and "href='https://" not in html_unknown
    assert "Cost: unknown (no data)" in html_unknown or "unknown (no data)" in html_unknown

    # Empty report produces placeholders for all views
    report_empty = build_report([])
    html_empty = render_html(report_empty)
    assert html_empty.count("<svg") >= 3
    assert "<script" not in html_empty.lower()
    assert "unknown (no data)" in html_empty


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



def test_csv_header_cells_derived_from_row_keys_are_formula_escaped():
    report = build_report([{"attempt_id": "a-1", "=HYPERLINK(1)": "x", "+SUM(1)": "x", "-MIN(1)": "x", "@REF": "x"}])
    header = render_csv(report).splitlines()[0].split(",")
    assert "attempt_id" in header
    assert not [cell for cell in header if cell.startswith(("=", "+", "-", "@"))]
