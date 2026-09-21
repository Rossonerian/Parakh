"""Compatibility shim for application reporting workflows."""

from model_lab.application.reporting import (
    REPORT_VERSION,
    build_report,
    render_csv,
    render_html,
    render_json,
    render_markdown,
    write_report_bundle,
)

__all__ = [
    "REPORT_VERSION",
    "build_report",
    "render_csv",
    "render_html",
    "render_json",
    "render_markdown",
    "write_report_bundle",
]
