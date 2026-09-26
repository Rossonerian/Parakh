"""Blind review manifests with deterministic anonymization."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .errors import ValidationError
from .schemas import Attempt, Case, HumanReview, stable_hash


def _label(attempt: Attempt) -> str:
    return f"candidate-{stable_hash({'run': attempt.run_id, 'case': attempt.case_id, 'attempt': attempt.attempt_id})[:12]}"


def export_blind_review(attempts: Iterable[Attempt], *, include_prompt: bool = False, cases: Iterable[Case] = ()) -> list[dict[str, Any]]:
    """Export only review material; provider/model and operational metrics never cross this boundary."""
    output = []
    case_by_id = {case.case_id: case for case in cases}
    for attempt in sorted(attempts, key=lambda item: (item.case_id, item.attempt_id)):
        row = {"review_id": f"review-{stable_hash({'attempt': attempt.attempt_id})[:24]}",
               # Keep a stable grouping key without exposing source run IDs,
               # which may contain a provider or model name.
               "run_id": f"blind-run-{stable_hash({'run': attempt.run_id})[:16]}",
               "case_id": attempt.case_id, "blind_label": _label(attempt), "candidate_output": attempt.response_text,
               "status": attempt.status.value}
        if include_prompt:
            case = case_by_id.get(attempt.case_id)
            if case is None or case.prompt_hash != attempt.prompt_hash:
                raise ValidationError("case prompt does not match attempt prompt hash")
            row["prompt"] = [dict(message) for message in case.messages]
        output.append(row)
    return output


def review_bindings(attempts: Iterable[Attempt]) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for attempt in attempts:
        label = _label(attempt)
        if label in bindings:
            raise ValidationError(f"duplicate blind label: {label}")
        bindings[label] = {"review_id": f"review-{stable_hash({'attempt': attempt.attempt_id})[:24]}", "run_id": f"blind-run-{stable_hash({'run': attempt.run_id})[:16]}", "case_id": attempt.case_id, "attempt_id": attempt.attempt_id, "actual_run_id": attempt.run_id}
    return bindings


def import_blind_reviews(records: Iterable[Mapping[str, Any]], *, expected_labels: Mapping[str, Mapping[str, str]] | None = None) -> list[HumanReview]:
    if expected_labels is None:
        raise ValidationError("expected blind-review bindings are required")
    reviews = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        required = ("review_id", "run_id", "case_id", "blind_label", "decision", "reviewer_pseudonym")
        missing = [key for key in required if not record.get(key)]
        if missing:
            raise ValidationError(f"review missing required fields: {', '.join(missing)}")
        review_key = (str(record["review_id"]), str(record["reviewer_pseudonym"]))
        if review_key in seen:
            raise ValidationError(f"duplicate review ID: {record['review_id']}")
        seen.add(review_key)
        binding = expected_labels.get(str(record["blind_label"]))
        if binding is None:
            raise ValidationError(f"unknown blind label: {record['blind_label']}")
        for field in ("review_id", "run_id", "case_id"):
            if str(record[field]) != str(binding.get(field)):
                raise ValidationError(f"blind review {field} does not match exported binding")
        if any(key in record for key in ("model", "provider", "cost", "latency", "ranking")):
            raise ValidationError("blind review contains operational identity or ranking data")
        derived_id = f"review-{stable_hash({'source_review_id': record['review_id'], 'reviewer': record['reviewer_pseudonym']})[:24]}"
        reviews.append(HumanReview(review_id=derived_id, run_id=str(binding["actual_run_id"]), case_id=str(binding["case_id"]),
                                   blind_label=str(record["blind_label"]), reviewer_pseudonym=str(record["reviewer_pseudonym"]),
                                   decision=str(record["decision"]), score=record.get("score"), notes=record.get("notes"),
                                   confidence=record.get("confidence"), created_at=str(record.get("created_at") or "unknown"), attempt_id=str(binding["attempt_id"])))
    return reviews


def adjudication_summary(reviews: Iterable[HumanReview]) -> dict[str, Any]:
    """Summarize independent reviewer votes without creating grades."""
    grouped: dict[str, list[HumanReview]] = {}
    for review in reviews:
        grouped.setdefault(review.attempt_id or review.blind_label, []).append(review)
    rows = []
    for key, votes in sorted(grouped.items()):
        decisions = [vote.decision for vote in votes]
        distinct = sorted(set(decisions))
        rows.append({"attempt_id": key, "review_count": len(votes), "decisions": decisions, "conflict": len(distinct) > 1, "status": "conflict" if len(distinct) > 1 else "consensus" if distinct else "unassessed"})
    return {"review_count": sum(len(v) for v in grouped.values()), "attempt_count": len(rows), "conflict_count": sum(row["conflict"] for row in rows), "rows": rows, "grades_created": False, "limitations": ["Votes are human-review evidence only; no implicit deterministic or model grade is created."]}
