"""Versioned product-constraint map loading for draft routing evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ValidationError


ALLOWED_STATUSES = frozenset({"satisfied", "unavailable", "blocking"})
REQUIRED_CONSTRAINT_FIELDS = frozenset({"id", "category", "requirement", "status", "value", "required_for_activation", "citations"})


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_constraint_map(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid router constraint map: {source}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "router-constraint-map/0.2.0":
        raise ValidationError("unsupported router constraint map schema")
    constraints = value.get("constraints")
    if not isinstance(constraints, list) or not constraints:
        raise ValidationError("router constraint map must contain constraints")
    seen: set[str] = set()
    for index, item in enumerate(constraints):
        if not isinstance(item, dict) or set(item) != REQUIRED_CONSTRAINT_FIELDS:
            raise ValidationError(f"constraint {index} has unsupported or missing fields")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValidationError(f"constraint {index} has an invalid or duplicate id")
        seen.add(identifier)
        if item.get("status") not in ALLOWED_STATUSES:
            raise ValidationError(f"constraint {identifier} has invalid status")
        if not isinstance(item.get("required_for_activation"), bool):
            raise ValidationError(f"constraint {identifier} required_for_activation must be boolean")
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise ValidationError(f"constraint {identifier} requires source citations")
        for citation in citations:
            if not isinstance(citation, dict) or not {"source_file", "section", "source_sha256"} <= set(citation):
                raise ValidationError(f"constraint {identifier} has an invalid citation")
    return value


def evaluate_constraints(constraint_map: Mapping[str, Any]) -> dict[str, Any]:
    constraints = constraint_map.get("constraints", [])
    if not isinstance(constraints, list):
        raise ValidationError("constraint map constraints must be a list")
    grouped = {status: [] for status in sorted(ALLOWED_STATUSES)}
    required_blockers: list[str] = []
    for item in constraints:
        identifier = str(item["id"])
        status = str(item["status"])
        grouped[status].append(identifier)
        if item.get("required_for_activation") and status != "satisfied":
            required_blockers.append(identifier)
    return {
        "evaluated": len(constraints),
        "satisfied": sorted(grouped["satisfied"]),
        "unavailable": sorted(grouped["unavailable"]),
        "blocking": sorted(grouped["blocking"]),
        "required_activation_blockers": sorted(required_blockers),
        "activation_ready": not required_blockers,
    }
