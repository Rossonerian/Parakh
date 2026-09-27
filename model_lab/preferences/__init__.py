"""High-confidence preference pair extraction, classification, and dataset export.

Extracts pairwise preference data from telemetry runs, classifies user feedback with
calibrated confidence, enforces privacy and non-trainable category exclusions, and
exports approved preference datasets for alignment.
"""

from __future__ import annotations

from model_lab.preferences.confidence import classify
from model_lab.preferences.exporter import export_approved, readiness
from model_lab.preferences.extractor import extract_pairs, review
from model_lab.preferences.schema import (
    ALL_CATEGORIES,
    EXCLUDED_CATEGORIES,
    PREFERENCE_SCHEMA_VERSION,
    TRAINABLE_CATEGORIES,
    Classification,
    PreferencePair,
)

__all__ = [
    "ALL_CATEGORIES",
    "EXCLUDED_CATEGORIES",
    "PREFERENCE_SCHEMA_VERSION",
    "TRAINABLE_CATEGORIES",
    "Classification",
    "PreferencePair",
    "classify",
    "export_approved",
    "extract_pairs",
    "readiness",
    "review",
]
