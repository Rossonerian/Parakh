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
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping

from model_lab.schemas import to_dict

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
        row = dict(plain)
        # Normalize immutable Attempt records to the report-row contract.
        config = row.get("model_config")
        if isinstance(config, Mapping):
            row.setdefault("model", config.get("model"))
            row.setdefault("provider", config.get("provider"))
            row.setdefault("context_condition", config.get("context_condition"))
            row.setdefault("parameters", config.get("parameters"))
        if "latency_ms" not in row:
            row["latency_ms"] = row.get("completion_latency_ms")
        for key, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"nonfinite report metric: {key}")
        output.append(row)
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


def _latency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["latency_ms"] for row in rows if isinstance(row.get("latency_ms"), (int, float)) and not isinstance(row.get("latency_ms"), bool)]
    values.sort()
    def percentile(p: float) -> float | None:
        if not values: return None
        return values[min(len(values) - 1, max(0, int(math.ceil(p * len(values))) - 1))]
    return {"known_count": len(values), "unknown_count": len(rows) - len(values), "median": statistics.median(values) if values else None,
            "p90": percentile(.90), "p95": percentile(.95), "tail_unstable": len(values) < 10}


def _cost(rows: list[dict[str, Any]]) -> dict[str, Any]:
    known = [
        row for row in rows
        if isinstance(row.get("cost_minor"), (int, float)) and not isinstance(row.get("cost_minor"), bool)
    ]
    currencies = {row.get("currency") for row in known}
    has_missing_currency = (None in currencies) or ("" in currencies)
    valid_currencies = {c for c in currencies if c not in (None, "")}

    if not known:
        currency_consistent = True
        currency = None
    elif has_missing_currency or len(valid_currencies) > 1:
        currency_consistent = False
        currency = None
    else:
        currency_consistent = True
        currency = next(iter(valid_currencies))

    complete = (
        len(known) == len(rows)
        and bool(rows)
        and currency_consistent
        and (currency is not None)
    )
    observed_subtotal = (
        sum(row["cost_minor"] for row in known)
        if (known and currency_consistent)
        else None
    )
    total_minor = sum(row["cost_minor"] for row in known) if complete else None

    return {
        "observed_subtotal_minor": observed_subtotal,
        "currency": currency,
        "currency_consistent": currency_consistent,
        "known_count": len(known),
        "unknown_count": len(rows) - len(known),
        "complete": complete,
        "total_minor": total_minor,
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
            "latency_ms": _latency(rows),
            "cost_minor": _cost(rows),
            "coverage": {
                "rows": len(rows),
                "cases_known": sum(bool(row.get("case_id")) for row in rows),
                "response_known": sum(row.get("response_text") is not None or row.get("output") is not None for row in rows),
                "quality_known": sum(isinstance(row.get("score"), (int, float)) and not isinstance(row.get("score"), bool) for row in rows),
                "latency_known": sum(isinstance(row.get("latency_ms"), (int, float)) and not isinstance(row.get("latency_ms"), bool) for row in rows),
                "cost_known": sum(isinstance(row.get("cost_minor"), (int, float)) and not isinstance(row.get("cost_minor"), bool) for row in rows),
                "context_condition_known": sum(bool(row.get("context_condition")) for row in rows),
                "critical_assessed": sum(row.get("critical_assessment") not in (None, "unassessed") for row in rows),
            },
        },
        "by_model": _group_summary(rows, "model"),
        "by_domain": _group_summary(rows, "domain"),
        "by_workflow": _group_summary(rows, "workflow"),
        "by_complexity": _group_summary(rows, "complexity_level"),
        "by_split": _group_summary(rows, "split"),
        "by_context_condition": _group_summary(rows, "context_condition"),
        "limitations": [
            "Unknown measurements are excluded from metric denominators and remain null.",
            "Synthetic or imported rows are not evidence of real-world model quality unless provenance says so.",
        ],
        "rows": rows,
    }
    verified = [
        row for row in rows
        if row.get("passed") is True and row.get("critical_assessment") not in (None, "unassessed")
    ]
    verified_success_count = len(verified)
    report["summary"]["verified_success_count"] = verified_success_count
    cost = report["summary"]["cost_minor"]
    report["summary"]["cost_per_verified_success"] = (
        (cost["total_minor"] / verified_success_count)
        if cost.get("complete") and cost.get("total_minor") is not None and verified_success_count > 0
        else None
    )
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
    writer.writerow({field: _csv_safe(field) for field in fields})
    for row in rows:
        writer.writerow({field: _csv_safe(row.get(field)) for field in fields})
    return stream.getvalue()


def _markdown_label_escape(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("|", "\\|")
    return text


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    quality = summary.get("quality", {})
    cost_per_vs = summary.get("cost_per_verified_success")
    mean_score = quality.get("mean_score")

    lines = [
        "# ModelLab report",
        "",
        f"- Report version: `{_markdown_label_escape(report.get('report_version', 'unknown'))}`",
        f"- Rows: `{summary.get('row_count', 0)}`",
        f"- Mean score: `{_markdown_label_escape(mean_score) if mean_score is not None else 'unknown'}`",
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
    lines += [
        "",
        f"- Cost per verified success: `{_markdown_label_escape(cost_per_vs) if cost_per_vs is not None else 'unknown'}`",
        f"- Verified successes: `{summary.get('verified_success_count', 0)}`",
        "",
        "## By model",
        "",
        "| Model | Rows | Mean score |",
        "| --- | ---: | ---: |",
    ]
    for model, values in report.get("by_model", {}).items():
        score = values["quality"].get("mean_score")
        score_str = "unknown" if score is None else str(score)
        lines.append(f"| {_markdown_label_escape(model)} | {values['count']} | {_markdown_label_escape(score_str)} |")
    lines += [
        "",
        "## By context condition",
        "",
        "| Condition | Rows | Mean score |",
        "| --- | ---: | ---: |",
    ]
    for condition, values in report.get("by_context_condition", {}).items():
        score = values["quality"].get("mean_score")
        score_str = "unknown" if score is None else str(score)
        lines.append(f"| {_markdown_label_escape(condition)} | {values['count']} | {_markdown_label_escape(score_str)} |")
    lines += [
        "",
        "## Provenance",
        "",
        "```json",
        json.dumps(report.get("provenance", {}), sort_keys=True),
        "```",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {_markdown_label_escape(item)}" for item in report.get("limitations", []))
    return "\n".join(lines) + "\n"


def _svg_cost_vs_verified_success(summary: Mapping[str, Any]) -> str:
    cost = summary.get("cost_minor", {})
    total = cost.get("total_minor")
    currency = cost.get("currency")
    complete = cost.get("complete", False)
    verified_count = summary.get("verified_success_count", 0)
    cost_per_vs = summary.get("cost_per_verified_success")

    width, height = 760, 200
    title = "Cost versus verified success"
    safe_title = html.escape(title, quote=True)

    cost_known = complete and (total is not None) and (currency is not None)
    if not cost_known:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="{safe_title}">\n'
            f'  <text x="20" y="30" font-size="16" font-weight="bold">{safe_title}</text>\n'
            f'  <rect x="20" y="50" width="720" height="120" fill="#f8f9fa" stroke="#e0e0e0" rx="4"/>\n'
            f'  <text x="40" y="85" font-size="14" fill="#666">Cost: unknown (no data)</text>\n'
            f'  <text x="40" y="115" font-size="14" fill="#333">Verified successes: {verified_count}</text>\n'
            f'  <text x="40" y="145" font-size="14" fill="#666">Cost per verified success: unknown</text>\n'
            f'</svg>\n'
        )

    safe_currency = html.escape(str(currency), quote=True)
    if verified_count > 0 and cost_per_vs is not None:
        cost_per_vs_text = f"{cost_per_vs:.4g} {safe_currency}"
    else:
        cost_per_vs_text = "unknown (0 verified successes)"

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="{safe_title}">\n'
        f'  <text x="20" y="30" font-size="16" font-weight="bold">{safe_title}</text>\n'
        f'  <rect x="20" y="50" width="220" height="120" fill="#f0f4f8" stroke="#cbd5e1" rx="6"/>\n'
        f'  <text x="40" y="80" font-size="12" fill="#64748b" font-weight="bold">TOTAL COST</text>\n'
        f'  <text x="40" y="115" font-size="18" fill="#1e293b" font-weight="bold">{total} {safe_currency}</text>\n'
        f'  <rect x="260" y="50" width="220" height="120" fill="#f0fdf4" stroke="#bbf7d0" rx="6"/>\n'
        f'  <text x="280" y="80" font-size="12" fill="#16a34a" font-weight="bold">VERIFIED SUCCESSES</text>\n'
        f'  <text x="280" y="115" font-size="18" fill="#1e293b" font-weight="bold">{verified_count}</text>\n'
        f'  <rect x="500" y="50" width="240" height="120" fill="#faf5ff" stroke="#e9d5ff" rx="6"/>\n'
        f'  <text x="520" y="80" font-size="12" fill="#9333ea" font-weight="bold">COST / VERIFIED SUCCESS</text>\n'
        f'  <text x="520" y="115" font-size="18" fill="#1e293b" font-weight="bold">{cost_per_vs_text}</text>\n'
        f'</svg>\n'
    )


def _svg_bars(values: Mapping[str, float | None], title: str) -> str:
    width, height = 760, 400
    safe_title = html.escape(title, quote=True)
    known_values = [v for v in values.values() if v is not None]
    if not values or not known_values:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="160" role="img" aria-label="{safe_title}">\n'
            f'  <text x="20" y="30" font-size="18" font-weight="bold">{safe_title}</text>\n'
            f'  <rect x="20" y="50" width="720" height="80" fill="#f8f9fa" stroke="#e0e0e0" rx="4"/>\n'
            f'  <text x="40" y="95" font-size="14" fill="#666">unknown (no data)</text>\n'
            f'</svg>\n'
        )
    max_value = max(known_values, default=1.0) or 1.0
    bar_width = max(1, (width - 80) // max(1, len(values)))
    bars = []
    for index, (label, value) in enumerate(sorted(values.items())):
        x = 50 + index * bar_width
        safe_label = html.escape(str(label), quote=True)
        if value is None:
            bars.append(f'<text x="{x}" y="315" font-size="11" fill="#888">unknown</text>')
            bars.append(f'<text x="{x}" y="350" font-size="11" transform="rotate(30 {x} 350)">{safe_label}</text>')
        else:
            bar_height = int(280 * max(0.0, value) / max_value)
            y = 330 - bar_height
            bars.append(f'<rect x="{x}" y="{y}" width="{max(1, bar_width - 8)}" height="{bar_height}" fill="#3568a8"><title>{safe_label}: {value:.4g}</title></rect>')
            bars.append(f'<text x="{x}" y="350" font-size="11" transform="rotate(30 {x} 350)">{safe_label}</text>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="{safe_title}"><text x="20" y="25" font-size="18">{safe_title}</text><line x1="45" y1="330" x2="740" y2="330" stroke="#333"/>{"".join(bars)}</svg>\n'


def render_html(report: Mapping[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape("unknown" if value is None else str(value), quote=True)

    summary = report.get("summary", {})
    quality = summary.get("quality", {})
    table_rows = "".join(
        "<tr>" + "".join(f"<td>{esc(row.get(field))}</td>" for field in ("attempt_id", "case_id", "model", "status", "score", "latency_ms", "response_text")) + "</tr>"
        for row in report.get("rows", [])
    )

    rows = report.get("rows", [])
    has_model = any("model" in r for r in rows)
    has_domain = any("domain" in r for r in rows)
    has_context = any("context_condition" in r for r in rows)

    model_scores = {
        model: values["quality"].get("mean_score")
        for model, values in report.get("by_model", {}).items()
        if model != "unknown" or has_model
    }
    domain_scores = {
        domain: values["quality"].get("mean_score")
        for domain, values in report.get("by_domain", {}).items()
        if domain != "unknown" or has_domain
    }
    context_scores = {
        cond: values["quality"].get("mean_score")
        for cond, values in report.get("by_context_condition", {}).items()
        if cond != "unknown" or has_context
    }

    svg_quality_model = _svg_bars(model_scores, "Quality by model")
    svg_quality_domain = _svg_bars(domain_scores, "Quality by domain")
    svg_cost = _svg_cost_vs_verified_success(summary)
    svg_context = _svg_bars(context_scores, "Performance by context condition")

    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><title>ModelLab report</title>"
        "<style>body{font-family:sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.35rem;text-align:left}th{background:#eee}.report-view{margin:2rem 0}</style>"
        f"</head><body><h1>ModelLab report</h1><p>Rows: {esc(summary.get('row_count'))}; mean score: {esc(quality.get('mean_score'))}</p>"
        "<h2>Views</h2>"
        f"<section class=\"report-view\">{svg_quality_model}</section>"
        f"<section class=\"report-view\">{svg_quality_domain}</section>"
        f"<section class=\"report-view\">{svg_cost}</section>"
        f"<section class=\"report-view\">{svg_context}</section>"
        "<h2>Attempts</h2><table><thead><tr><th>Attempt</th><th>Case</th><th>Model</th><th>Status</th><th>Score</th><th>Latency (ms)</th><th>Response</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table><h2>Limitations</h2><ul>"
        + "".join(f"<li>{esc(item)}</li>" for item in report.get("limitations", []))
        + "</ul></body></html>\n"
    )


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
