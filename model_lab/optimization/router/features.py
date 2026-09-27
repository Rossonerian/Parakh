"""routing-features.v1: declarative, versioned feature extraction.

The schema below is exported verbatim as ``feature_schema.json`` in every
PolicyBundleV1, and both Parakh (here) and Karmi's loader compute vectors by
*interpreting* it, so the two sides cannot silently diverge. Raw prompt text is
never a feature. Changing any entry requires a new ``FEATURE_SCHEMA_VERSION``.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from model_lab.errors import ValidationError
from model_lab.schema_registry import FEATURE_SCHEMA_VERSION
from model_lab.schemas import DOMAINS, stable_hash

TIERS = ("ananta", "yanta", "trika", "part")


def _one_hot(source: str, values: tuple[str, ...]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [{"name": f"{source}={v}", "source": source, "transform": "equals", "value": v} for v in values]
    specs.append({"name": f"{source}=other", "source": source, "transform": "not_in", "values": list(values)})
    return specs


FEATURES: tuple[dict[str, Any], ...] = (
    {"name": "bias", "transform": "constant", "value": 1.0},
    *_one_hot("tier", TIERS),
    *_one_hot("task_domain", tuple(sorted(DOMAINS))),
    {"name": "log_input_tokens", "source": "estimated_input_tokens", "transform": "log1p_scaled", "scale": 200_000},
    {"name": "context_utilization", "source": "context_utilization_ratio", "transform": "clip01"},
    {"name": "tool_count", "source": "tool_count", "transform": "capped_ratio", "cap": 10},
    {"name": "requires_structured_output", "source": "requires_structured_output", "transform": "bool"},
    {"name": "requires_tools", "source": "requires_tools", "transform": "bool"},
    {"name": "requires_memory", "source": "requires_memory", "transform": "bool"},
    {"name": "requires_external_data", "source": "requires_external_data", "transform": "bool"},
    {"name": "conversation_depth", "source": "conversation_depth", "transform": "capped_ratio", "cap": 50},
    {"name": "retry_number", "source": "retry_number", "transform": "capped_ratio", "cap": 5},
    {"name": "previous_tool_failure", "source": "previous_tool_failure", "transform": "bool"},
    {"name": "has_latency_slo", "source": "latency_slo_ms", "transform": "present"},
    {"name": "latency_slo", "source": "latency_slo_ms", "transform": "capped_ratio", "cap": 30_000},
)


def _build_schema() -> dict[str, Any]:
    body = {"feature_schema_version": FEATURE_SCHEMA_VERSION, "dimension": len(FEATURES), "features": [dict(f) for f in FEATURES],
            "missing_value_policy": "optional sources absent or null -> 0.0; required sources absent -> reject context"}
    return {**body, "schema_id": stable_hash(body)[:16]}


_SCHEMA = _build_schema()


def feature_schema() -> dict[str, Any]:
    """The exportable ``feature_schema.json`` document (a fresh copy; the module constant is never exposed)."""
    return copy.deepcopy(_SCHEMA)


def _apply(spec: Mapping[str, Any], context: Mapping[str, Any]) -> float:
    transform = spec["transform"]
    if transform == "constant":
        return float(spec["value"])
    value = context.get(spec["source"])
    if transform == "present":
        return 0.0 if value is None else 1.0
    if value is None:
        if spec["source"] in ("latency_slo_ms",):
            return 0.0
        raise ValidationError(f"routing context missing {spec['source']}")
    if transform == "equals":
        return 1.0 if value == spec["value"] else 0.0
    if transform == "not_in":
        return 0.0 if value in spec["values"] else 1.0
    if transform == "bool":
        if not isinstance(value, bool):
            raise ValidationError(f"{spec['source']} must be boolean")
        return 1.0 if value else 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{spec['source']} must be a finite number")
    if transform == "clip01":
        return min(1.0, max(0.0, float(value)))
    if transform == "capped_ratio":
        return min(1.0, max(0.0, float(value) / float(spec["cap"])))
    if transform == "log1p_scaled":
        return min(1.0, math.log1p(max(0.0, float(value))) / math.log1p(float(spec["scale"])))
    raise ValidationError(f"unknown feature transform {transform}")


def extract(context: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> tuple[float, ...]:
    """Deterministic feature vector for a Karmi RoutingContext mapping."""
    specs = (schema or _SCHEMA)["features"]
    return tuple(_apply(spec, context) for spec in specs)
