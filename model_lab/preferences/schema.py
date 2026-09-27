"""Preference pair schema and classification data structures.

Defines preference pair records, feedback classification categories, and lifecycle states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from model_lab.schema_registry import PREFERENCE_SCHEMA_VERSION

TRAINABLE_CATEGORIES = (
    "true_correction",
    "factual_correction",
    "execution_repair",
)

EXCLUDED_CATEGORIES = (
    "changed_intent",
    "style_preference",
    "schedule_detail_change",
)

ALL_CATEGORIES = (
    "true_correction",
    "changed_intent",
    "style_preference",
    "factual_correction",
    "schedule_detail_change",
    "execution_repair",
    "ambiguous",
)


@dataclass(frozen=True)
class Classification:
    """Outcome of classifying user feedback for preference learning."""

    category: str
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PreferencePair:
    """Canonical preference pair extracted from user corrections."""

    pair_id: str
    prompt_or_context_ref: str
    chosen: str
    rejected: str
    confidence: float
    reason: str
    category: str
    source_run_id: str
    feedback_id: str
    schema_version: str = PREFERENCE_SCHEMA_VERSION
    approval_state: str = "PROPOSED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "prompt_or_context_ref": self.prompt_or_context_ref,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "confidence": self.confidence,
            "reason": self.reason,
            "category": self.category,
            "source_run_id": self.source_run_id,
            "feedback_id": self.feedback_id,
            "schema_version": self.schema_version,
            "approval_state": self.approval_state,
        }
