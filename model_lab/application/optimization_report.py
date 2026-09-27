"""Optimization decision report: Evidence / Analysis / Decision, never one opaque score.

Renders a verification report (plus optional compounding metrics) to JSON,
Markdown and self-contained HTML. Every interpolated value is escaped (HTML
entities; Markdown labels cannot start lines, inject headings or raw HTML);
the HTML has no scripts and no external resources.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping

from model_lab.application.reporting import _markdown_label_escape as _markdown_escape


def md(value: Any) -> str:
    """Escape untrusted text even inside Markdown code spans."""
    return _markdown_escape(value).replace("`", "&#96;")


def _fmt(value: Any) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def sections(report: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    core = report.get("core_regression", {})
    ope = report.get("ope", {})
    return {
        "evidence": {
            "evidence_class": report.get("evidence_class"), "dataset_id": report.get("dataset_id"),
            "evaluation_run_ids": report.get("evaluation_run_ids", []), "human_review_run_ids": report.get("human_review_run_ids", []),
            "grader_versions": report.get("grader_versions", {}),
            "core_deterministic_pass_rate": {"candidate": core.get("candidate", {}).get("overall", {}).get("deterministic_pass_rate"),
                                             "baseline": core.get("baseline", {}).get("overall", {}).get("deterministic_pass_rate")},
            "core_latency_ms_mean": core.get("candidate", {}).get("overall", {}).get("latency_ms_mean"),
            "core_estimated_cost_mean_usd": core.get("candidate", {}).get("overall", {}).get("estimated_cost_mean"),
        },
        "analysis": {
            "validation_estimate": {k: ope.get("validation", {}).get(k) for k in ("snips", "ips", "dr", "ci", "ess", "support", "warnings")},
            "logging_value": ope.get("logging_validation", {}).get("value"),
            "holdout_estimate": {k: ope.get("holdout", {}).get(k) for k in ("snips", "ci", "warnings")},
            "soft_metrics": report.get("soft_metrics", {}), "compounding_metrics": dict(metrics or {}),
            "limitations": report.get("limitations", []),
        },
        "decision": {
            "policy_candidate_id": report.get("policy_candidate_id"), "report_id": report.get("report_id"), "passed": report.get("passed"),
            "failed_gates": report.get("failed_gates", []),
            "gates": [{"gate": g["gate"], "passed": g["passed"], "reason": g["reason"]} for g in report.get("hard_gates", [])],
        },
    }


def render_markdown(report: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> str:
    s = sections(report, metrics)
    decision = s["decision"]
    lines = ["# Parakh optimization report", "",
             f"- Candidate: `{md(decision['policy_candidate_id'])}`  Report: `{md(decision['report_id'])}`",
             f"- Evidence class: **{md(s['evidence']['evidence_class'])}**", "", "## Decision", "",
             f"**{'PASSED all hard gates' if decision['passed'] else 'FAILED'}**", "", "| Gate | Result | Reason |", "| --- | --- | --- |"]
    lines += [f"| {md(g['gate'])} | {'pass' if g['passed'] else 'FAIL'} | {md(g['reason'])} |" for g in decision["gates"]]
    lines += ["", "## Evidence", ""]
    lines += [f"- {md(k)}: `{md(_fmt(v) if not isinstance(v, (dict, list)) else json.dumps(v, sort_keys=True))}`" for k, v in s["evidence"].items()]
    lines += ["", "## Analysis", ""]
    for k, v in s["analysis"].items():
        if k == "limitations":
            continue
        lines.append(f"- {md(k)}: `{md(json.dumps(v, sort_keys=True, default=str))}`")
    lines += ["", "## Limitations", ""] + [f"- {md(item)}" for item in s["analysis"]["limitations"]]
    return "\n".join(lines) + "\n"


def _table(rows: list[tuple[str, str]]) -> str:
    return "<table>" + "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows) + "</table>"


def render_html(report: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> str:
    s = sections(report, metrics)
    decision = s["decision"]
    gates = "".join(f"<tr class=\"{'pass' if g['passed'] else 'fail'}\"><td>{html.escape(g['gate'])}</td><td>{'pass' if g['passed'] else 'FAIL'}</td>"
                    f"<td>{html.escape(str(g['reason']))}</td></tr>" for g in decision["gates"])
    evidence = _table([(k, _fmt(v) if not isinstance(v, (dict, list)) else json.dumps(v, sort_keys=True)) for k, v in s["evidence"].items()])
    analysis = _table([(k, json.dumps(v, sort_keys=True, default=str)) for k, v in s["analysis"].items() if k != "limitations"])
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in s["analysis"]["limitations"])
    verdict = "PASSED all hard gates" if decision["passed"] else "FAILED: " + ", ".join(decision["failed_gates"])
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>Parakh optimization report</title>"
            "<style>body{font-family:sans-serif;margin:2em}td,th{border:1px solid #ccc;padding:4px;text-align:left;vertical-align:top}"
            "table{border-collapse:collapse;margin-bottom:1em}.fail{background:#fdd}.pass{background:#dfd}</style></head><body>"
            f"<h1>Parakh optimization report</h1><p>Candidate <code>{html.escape(str(decision['policy_candidate_id']))}</code> · "
            f"evidence class <b>{html.escape(str(s['evidence']['evidence_class']))}</b></p>"
            f"<h2>Decision</h2><p><b>{html.escape(verdict)}</b></p><table><tr><th>Gate</th><th>Result</th><th>Reason</th></tr>{gates}</table>"
            f"<h2>Evidence</h2>{evidence}<h2>Analysis</h2>{analysis}<h2>Limitations</h2><ul>{limitations}</ul></body></html>\n")


def write(report: Mapping[str, Any], out_dir: str | Path, metrics: Mapping[str, Any] | None = None) -> dict[str, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = {"json": target / "optimization_report.json", "md": target / "optimization_report.md", "html": target / "optimization_report.html"}
    paths["json"].write_text(json.dumps(sections(report, metrics), sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    paths["md"].write_text(render_markdown(report, metrics), encoding="utf-8")
    paths["html"].write_text(render_html(report, metrics), encoding="utf-8")
    return paths
