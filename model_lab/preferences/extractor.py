"""High-confidence preference pair extraction and review lifecycle management.

Extracts pairwise preference candidates (chosen vs rejected) from telemetry feedback,
enforces privacy and category firewalls, and orchestrates the auditable approval state machine.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from model_lab.errors import ValidationError
from model_lab.preferences.confidence import classify
from model_lab.preferences.schema import (
    EXCLUDED_CATEGORIES,
    PREFERENCE_SCHEMA_VERSION,
    TRAINABLE_CATEGORIES,
)
from model_lab.schemas import stable_hash
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord

PRIVACY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.\+/=]{8,}", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]


def _contains_privacy_data(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) is not None for p in PRIVACY_PATTERNS)


def extract_pairs(
    evidence: EvidenceStore,
    runs: Iterable[RunRecord],
    *,
    min_confidence: float = 0.8,
) -> list[dict[str, Any]]:
    """Extract preference pairs from runs, classify feedback, apply privacy gates,

    and record transitions/records in the evidence store.
    """
    extracted: list[dict[str, Any]] = []

    for run in runs:
        for feedback in run.feedback:
            classification = classify(feedback, run)
            feedback_id = str(feedback.get("feedback_id", ""))
            pair_id = "pair-" + stable_hash({"feedback_id": feedback_id, "run_id": run.run_id})[:20]
            prompt_or_context_ref = f"traj-{run.run_id}"

            # Only the contract's sanitized fields may become training text (TelemetryBatchV1 feedback).
            chosen = feedback.get("sanitized_corrected_value")
            rejected = feedback.get("sanitized_original_value")

            chosen_str = str(chosen) if chosen is not None else ""
            rejected_str = str(rejected) if rejected is not None else ""

            reasons_list = list(classification.reasons)
            category = classification.category

            privacy_hit = _contains_privacy_data(chosen_str) or _contains_privacy_data(rejected_str)

            if privacy_hit:
                target_state = "EXCLUDED"
                reasons_list.append("privacy")
            elif not chosen_str.strip():
                target_state = "EXCLUDED"
                reasons_list.append("missing_chosen_text")
            elif not rejected_str.strip():
                target_state = "EXCLUDED"
                reasons_list.append("missing_rejected_text")
            elif category in EXCLUDED_CATEGORIES:
                target_state = "EXCLUDED"
                reasons_list.append(f"excluded_category_{category}")
            elif category == "ambiguous" or classification.confidence < min_confidence:
                target_state = "NEEDS_REVIEW"
                if category == "ambiguous":
                    reasons_list.append("ambiguous_category")
                if classification.confidence < min_confidence:
                    reasons_list.append(f"low_confidence_{classification.confidence:.2f}")
            elif category in TRAINABLE_CATEGORIES:
                target_state = "PROPOSED"
                reasons_list.append("high_confidence_trainable")
            else:
                target_state = "EXCLUDED"
                reasons_list.append(f"unknown_category_{category}")

            reason_str = "; ".join(reasons_list)

            current_state = evidence.state("preference_pair", pair_id)
            if current_state is None:
                evidence.transition(
                    "preference_pair",
                    pair_id,
                    target_state,
                    actor="preference_extractor",
                    reason=reason_str,
                )
                final_state = target_state
            else:
                final_state = current_state

            record = {
                "pair_id": pair_id,
                "prompt_or_context_ref": prompt_or_context_ref,
                "chosen": chosen_str,
                "rejected": rejected_str,
                "confidence": classification.confidence,
                "reason": reason_str,
                "category": category,
                "source_run_id": run.run_id,
                "feedback_id": feedback_id,
                "schema_version": PREFERENCE_SCHEMA_VERSION,
                "initial_state": target_state,
            }

            evidence.append("preference_pairs", pair_id, record)
            extracted.append({**record, "approval_state": final_state})

    return extracted


def review(
    evidence: EvidenceStore,
    pair_id: str,
    decision: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Execute lifecycle transition for a preference pair based on review decision.

    Decisions:
    - 'propose': NEEDS_REVIEW -> PROPOSED
    - 'approve': PROPOSED -> APPROVED
    - 'reject': PROPOSED -> REJECTED, APPROVED -> REJECTED, or NEEDS_REVIEW -> EXCLUDED
    """
    current_state = evidence.state("preference_pair", pair_id)
    if current_state is None:
        raise ValidationError(f"unknown preference pair: {pair_id}")

    if current_state == "NEEDS_REVIEW":
        if decision == "propose":
            to_state = "PROPOSED"
        elif decision in ("reject", "exclude"):
            to_state = "EXCLUDED"
        else:
            raise ValidationError(f"invalid decision '{decision}' for state '{current_state}'")
    elif current_state == "PROPOSED":
        if decision == "approve":
            to_state = "APPROVED"
        elif decision == "reject":
            to_state = "REJECTED"
        else:
            raise ValidationError(f"invalid decision '{decision}' for state '{current_state}'")
    elif current_state == "APPROVED":
        if decision == "reject":
            to_state = "REJECTED"
        else:
            raise ValidationError(f"invalid decision '{decision}' for state '{current_state}'")
    else:
        raise ValidationError(f"cannot review pair {pair_id} in state {current_state}")

    return evidence.transition(
        "preference_pair",
        pair_id,
        to_state,
        actor=actor,
        reason=reason,
    )
