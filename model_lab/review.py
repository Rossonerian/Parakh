"""Blind review manifests with deterministic anonymization."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .schemas import Attempt, HumanReview, stable_hash, utc_now


def _label(attempt: Attempt) -> str:
    return f"candidate-{stable_hash({'run': attempt.run_id, 'case': attempt.case_id, 'attempt': attempt.attempt_id})[:12]}"


def export_blind_review(attempts: Iterable[Attempt], *, include_prompt: bool = False) -> list[dict[str, Any]]:
    """Export only review material; provider/model and operational metrics never cross this boundary."""
    output = []
    for attempt in sorted(attempts, key=lambda item: (item.case_id, item.attempt_id)):
        row = {"review_id": f"review-{stable_hash({'attempt': attempt.attempt_id})[:24]}",
               # Keep a stable grouping key without exposing source run IDs,
               # which may contain a provider or model name.
               "run_id": f"blind-run-{stable_hash({'run': attempt.run_id})[:16]}",
               "case_id": attempt.case_id, "blind_label": _label(attempt), "candidate_output": attempt.response_text,
               "status": attempt.status.value}
        if include_prompt:
            row["prompt_hash"] = attempt.prompt_hash
        output.append(row)
    return output


def import_blind_reviews(records: Iterable[Mapping[str, Any]], *, expected_labels: Mapping[str, Mapping[str, str]] | None = None) -> list[HumanReview]:
    reviews = []
    seen: set[str] = set()
    for record in records:
        required = ("review_id", "run_id", "case_id", "blind_label", "decision", "reviewer_pseudonym")
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise ValidationError(f"review missing required fields: {', '.join(missing)}")
        if record["review_id"] in seen:
            raise ValidationError(f"duplicate review ID: {record['review_id']}")
        seen.add(record["review_id"])
        if expected_labels and record["blind_label"] not in expected_labels:
            raise ValidationError(f"unknown blind label: {record['blind_label']}")
        if any(key in record for key in ("model", "provider", "cost", "latency", "ranking")):
            raise ValidationError("blind review contains operational identity or ranking data")
        reviews.append(HumanReview(review_id=str(record["review_id"]), run_id=str(record["run_id"]), case_id=str(record["case_id"]),
                                   blind_label=str(record["blind_label"]), reviewer_pseudonym=str(record["reviewer_pseudonym"]),
                                   decision=str(record["decision"]), score=record.get("score"), notes=record.get("notes"),
                                   confidence=record.get("confidence"), created_at=str(record.get("created_at") or utc_now())))
    return reviews
