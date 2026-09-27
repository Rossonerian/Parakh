"""Rubric and human review quality component evaluation.

Computes rubric quality score H from blind human reviews with accept/reject decisions,
excluding abstained or tied reviews.
"""

from __future__ import annotations

from typing import Iterable

from model_lab.schemas import HumanReview
from model_lab.telemetry.schema import RunRecord


def rubric_from_reviews(reviews: Iterable[HumanReview] | None) -> tuple[float | None, str | None]:
    """Compute rubric score H from human review decisions (accept/reject only).

    Returns:
        (H, signal_strength)
    """
    if not reviews:
        return None, None

    valid_scores = [
        r.score
        for r in reviews
        if r.decision in ("accept", "reject") and r.score is not None
    ]
    if not valid_scores:
        return None, None

    H = sum(valid_scores) / len(valid_scores)
    return H, "medium"


def rubric_for_run(run: RunRecord) -> tuple[float | None, str | None]:
    """Telemetry runs carry no rubric / human review quality component."""
    return None, None
