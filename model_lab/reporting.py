"""Deterministic, dependency-light ModelLab report generation.

Reports are derived from observed records.  Missing measurements remain null and
are counted as unknown; they are never converted into zeroes.
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .schemas import canonical_record, to_dict

REPORT_VERSION = "model_lab.report/v1"
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _plain(value: Any) -> Any:
    converted = to_dict(value)
    if isinstance(converted, Mapping):
        return {str(k): _plain(v) for k, v in converted.items()}
    if isinstance(converted, (list, tuple)):
        return [_plain(v) for v in converted]
    return converted


def _records(records: Iterable[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in records:
        plain = _plain(record)
        if not isinstance(plain, dict):
            raise TypeError("report records must be mappings or dataclasses")
        output.append(dict(plain))
    return sorted(output, key=lambda row: (str(row.get("attempt_id", "")), str(row.get("case_id", ""))))


def _metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [row[field] for row in rows if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)]
    return {
        "known_count": len(values),
        "unknown_count": len(rows) - len(values),
        "value": (sum(values) / len(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def _quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["score"]) for row in rows if isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool)]
    passed = [row["passed"] for row in rows if isinstance(row.get("passed"), bool)]
    return {
        "known_count": len(values),
        "unknown_count": len(rows) - len(values),
        "mean_score": sum(values) / len(values) if values else None,
        "passed_count": sum(value is True for value in passed),
        "failed_count": sum(value is False for value in passed),
        "passed_rate": (sum(value is True for value in passed) / len(passed)) if passed else None,
    }


def _group_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(field, "unknown")), []).append(row)
    return {key: {"count": len(group), "quality": _quality(group), "latency_ms": _metric(group, "latency_ms"), "cost_minor": _metric(group, "cost_minor")} for key, group in sorted(groups.items())}


def build_report(records: Iterable[Any], *, metadata: Mapping[str, Any] | None = None, provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a stable report object from attempts and/or derived result rows."""
    rows = _records(records)
    meta = {str(key): _plain(value) for key, value in (metadata or {}).items()}
    report = {
        "report_version": REPORT_VERSION,
        "metadata": meta,
        "provenance": {str(key): _plain(value) for key, value in (provenance or {}).items()},
        "summary": {
            "row_count": len(rows),
            "quality": _quality(rows),
            "latency_ms": _metric(rows, "latency_ms"),
            "cost_minor": _metric(rows, "cost_minor"),
            "coverage": {
                "rows": len(rows),
                "cases_known": sum(bool(row.get("case_id")) for row in rows),
                "response_known": sum(row.get("response_text") is not None or row.get("output") is not None for row in rows),
                "quality_known": sum(isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool) for row in rows),
                "latency_known": sum(isinstance(row.get("latency_ms"), (int, float)) and not isinstance(row.get("latency_ms"), bool) for row in rows),
                "cost_known": sum(isinstance(row.get("cost_minor"), (int, float)) and not isinstance(row.get("cost_minor"), bool) for row in rows),
            },
        },
        "by_model": _group_summary(rows, "model"),
        "by_domain": _group_summary(rows, "domain"),
        "by_workflow": _group_summary(rows, "workflow"),
        "by_complexity": _group_summary(rows, "complexity_level"),
        "by_split": _group_summary(rows, "split"),
        "limitations": [
            "Unknown measurements are excluded from metric denominators and remain null.",
            "Synthetic or imported rows are not evidence of real-world model quality unless provenance says so.",
        ],
        "rows": rows,
    }
    return report


def render_json(report: Mapping[str, Any]) -> str:
    return json.dumps(_plain(report), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def render_csv(report: Mapping[str, Any]) -> str:
    rows = list(report.get("rows", []))
    fields = sorted({str(key) for row in rows for key in row}) if rows else ["attempt_id", "case_id", "score", "status"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field)) for field in fields})
    return stream.getvalue()


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    quality = summary.get("quality", {})
    coverage = summary.get("coverage", {})
    lines = [
        "# ModelLab report",
        "",
        f"- Report version: `{report.get('report_version', 'unknown')}`",
        f"- Rows: `{summary.get('row_count', 0)}`",
        f"- Mean score: `{quality.get('mean_score') if quality.get('mean_score') is not None else 'unknown'}`",
        f"- Quality known/unknown: `{quality.get('known_count', 0)}/{quality.get('unknown_count', 0)}`",
        "",
        "## Coverage and unknown metrics",
        "",
        "| Metric | Known | Unknown |",
        "| --- | ---: | ---: |",
    ]
    for name in ("quality", "latency_ms", "cost_minor"):
        metric = summary.get(name, {})
        lines.append(f"| {name} | {metric.get('known_count', 0)} | {metric.get('unknown_count', 0)} |")
    lines += ["", "## By model", "", "| Model | Rows | Mean score |", "| --- | ---: | ---: |"]
    for model, values in report.get("by_model", {}).items():
        lines.append(f"| {model.replace('|', '\\|')} | {values['count']} | {values['quality'].get('mean_score', 'unknown')} |")
    lines += ["", "## Provenance", "", "```json", json.dumps(report.get("provenance", {}), sort_keys=True), "```", "", "## Limitations", ""]
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    return "\n".join(lines) + "\n"


def render_html(report: Mapping[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape("unknown" if value is None else str(value), quote=True)

    summary = report.get("summary", {})
    quality = summary.get("quality", {})
    table_rows = "".join(
        "<tr>" + "".join(f"<td>{esc(row.get(field))}</td>" for field in ("attempt_id", "case_id", "model", "status", "score", "latency_ms", "response_text")) + "</tr>"
        for row in report.get("rows", [])
    )
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>ModelLab report</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.35rem;text-align:left}th{background:#eee}</style>"
        f"</head><body><h1>ModelLab report</h1><p>Rows: {esc(summary.get('row_count'))}; mean score: {esc(quality.get('mean_score'))}</p>"
        "<h2>Attempts</h2><table><thead><tr><th>Attempt</th><th>Case</th><th>Model</th><th>Status</th><th>Score</th><th>Latency (ms)</th><th>Response</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table><h2>Limitations</h2><ul>"
        + "".join(f"<li>{esc(item)}</li>" for item in report.get("limitations", []))
        + "</ul></body></html>\n"
    )


def _svg_bars(values: Mapping[str, float], title: str) -> str:
    width, height = 760, 400
    max_value = max(values.values(), default=1.0) or 1.0
    bar_width = max(1, (width - 80) // max(1, len(values)))
    bars = []
    for index, (label, value) in enumerate(sorted(values.items())):
        x = 50 + index * bar_width
        bar_height = int(280 * max(0.0, value) / max_value)
        y = 330 - bar_height
        safe_label = html.escape(label, quote=True)
        bars.append(f'<rect x="{x}" y="{y}" width="{max(1, bar_width - 8)}" height="{bar_height}" fill="#3568a8"><title>{safe_label}: {value:.4g}</title></rect>')
        bars.append(f'<text x="{x}" y="350" font-size="11" transform="rotate(30 {x} 350)">{safe_label}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="{html.escape(title, quote=True)}"><text x="20" y="25" font-size="18">{html.escape(title)}</text><line x1="45" y1="330" x2="740" y2="330" stroke="#333"/>{"".join(bars)}</svg>\n'


def _write_optional_png(path: Path, values: Mapping[str, float], title: str) -> bool:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return False
    figure, axis = plt.subplots(figsize=(8, 4))
    axis.bar(list(values), list(values.values()), color="#3568a8")
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(path, format="png")
    plt.close(figure)
    return True


def write_report_bundle(records: Iterable[Any] | Mapping[str, Any], output_dir: str | Path, *, metadata: Mapping[str, Any] | None = None, provenance: Mapping[str, Any] | None = None) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report = dict(records) if isinstance(records, Mapping) and "summary" in records else build_report(records, metadata=metadata, provenance=provenance)
    paths = {
        "json": destination / "report.json",
        "csv": destination / "report.csv",
        "markdown": destination / "report.md",
        "html": destination / "report.html",
    }
    paths["json"].write_text(render_json(report), encoding="utf-8")
    paths["csv"].write_text(render_csv(report), encoding="utf-8", newline="")
    paths["markdown"].write_text(render_markdown(report), encoding="utf-8")
    paths["html"].write_text(render_html(report), encoding="utf-8")
    model_values = {key: value["quality"]["mean_score"] for key, value in report.get("by_model", {}).items() if value["quality"].get("mean_score") is not None}
    latency_values = {row.get("attempt_id", str(index)): row["latency_ms"] for index, row in enumerate(report.get("rows", [])) if isinstance(row.get("latency_ms"), (int, float))}
    charts: dict[str, Any] = {}
    for name, values, title in (("quality_by_model", model_values, "Quality by model"), ("latency_distribution", latency_values, "Observed latency (ms)")):
        svg_path = destination / f"{name}.svg"
        svg_path.write_text(_svg_bars(values, title), encoding="utf-8")
        paths[name] = svg_path
        png_path = destination / f"{name}.png"
        if values and _write_optional_png(png_path, values, title):
            paths[f"{name}_png"] = png_path
            charts[name] = {"svg": "available", "png": "available"}
        else:
            charts[name] = {"svg": "available", "png": "skipped", "reason": "PNG chart skipped: matplotlib optional dependency unavailable or no measured values"}
    paths["charts"] = destination / "charts.json"
    paths["charts"].write_text(json.dumps(charts, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return paths


generate_report = build_report
write_reports = write_report_bundle
