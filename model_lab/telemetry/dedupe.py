"""Deduplication and similarity scoring for telemetry runs.

Provides exact key hashing (content invariance across run metadata),
structural signatures for behavioral grouping, and text similarity metrics.
Deduplication never deletes runs; it establishes relationships and lineage.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from model_lab.schemas import stable_hash
from model_lab.telemetry.schema import RunRecord

EXCLUDED_EXACT_KEYS = frozenset({
    "run_id",
    "request_id",
    "session_id_hash",
    "decision_id",
    "attempt_id",
    "event_id",
    "feedback_id",
    "started_at",
    "completed_at",
    "created_at",
    "finalized_at",
})


def _strip_exact_keys(val: Any) -> Any:
    if isinstance(val, Mapping):
        return {k: _strip_exact_keys(v) for k, v in val.items() if k not in EXCLUDED_EXACT_KEYS}
    if isinstance(val, list):
        return [_strip_exact_keys(item) for item in val]
    if isinstance(val, tuple):
        return tuple(_strip_exact_keys(item) for item in val)
    return val


def exact_key(run: RunRecord) -> str:
    """Stable hash of run.raw stripped of run/request/decision/attempt/event IDs, timestamps, and session hash."""
    cleaned = _strip_exact_keys(run.raw)
    return stable_hash(cleaned)


def _token_bucket(tokens: int) -> str:
    if tokens < 1000:
        return "<1k"
    if tokens < 4000:
        return "<4k"
    if tokens < 16000:
        return "<16k"
    if tokens < 64000:
        return "<64k"
    return ">=64k"


def structural_signature(run: RunRecord) -> str:
    """Stable hash of domain, tier, token bucket, requires flags, tool names, live action, and outcome failure signature."""
    context = run.routing_context
    tokens = int(context.get("estimated_input_tokens", 0))
    bucket = _token_bucket(tokens)

    requires_flags = (
        bool(context.get("requires_structured_output", False)),
        bool(context.get("requires_tools", False)),
        bool(context.get("requires_memory", False)),
        bool(context.get("requires_external_data", False)),
    )

    tool_names = sorted({e["tool_name"] for e in run.tool_events if isinstance(e, Mapping) and "tool_name" in e})

    errors: set[str] = set()
    for att in run.attempts:
        if isinstance(att, Mapping) and att.get("error_type") is not None:
            errors.add(str(att["error_type"]))
    for te in run.tool_events:
        if isinstance(te, Mapping) and te.get("error_class") is not None:
            errors.add(str(te["error_class"]))
    for ve in run.validation_events:
        if isinstance(ve, Mapping) and ve.get("error_class") is not None:
            errors.add(str(ve["error_class"]))

    completed = run.outcome.get("completed") if isinstance(run.outcome, Mapping) else None
    failure_sig = (sorted(errors), bool(completed) if completed is not None else None)

    signature_data = {
        "task_domain": run.task_domain,
        "tier": run.tier,
        "token_bucket": bucket,
        "requires_flags": requires_flags,
        "tool_names": tool_names,
        "live_action": run.live_decision.action,
        "failure_signature": failure_sig,
    }
    return stable_hash(signature_data)


def _extract_feedback_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "feedback"):
        feedbacks = obj.feedback
    elif isinstance(obj, Mapping):
        feedbacks = obj.get("feedback", [])
    elif isinstance(obj, (list, tuple)):
        feedbacks = obj
    else:
        return ""
    texts: list[str] = []
    for fb in feedbacks:
        if isinstance(fb, Mapping):
            for k in ("sanitized_original_value", "sanitized_corrected_value", "feedback_text", "text"):
                val = fb.get(k)
                if isinstance(val, str) and val.strip():
                    texts.append(val.strip())
        elif isinstance(fb, str) and fb.strip():
            texts.append(fb.strip())
    return " ".join(texts)


def text_similarity(a: Any, b: Any) -> float:
    """Token Jaccard similarity over sanitized feedback text in [0, 1]."""
    text_a = _extract_feedback_text(a)
    text_b = _extract_feedback_text(b)
    tokens_a = set(re.findall(r"\w+", text_a.lower()))
    tokens_b = set(re.findall(r"\w+", text_b.lower()))

    if not tokens_a and not tokens_b:
        return 1.0 if (not text_a and not text_b) else 0.0
    union = tokens_a | tokens_b
    if not union:
        return 1.0
    intersection = tokens_a & tokens_b
    return len(intersection) / len(union)
