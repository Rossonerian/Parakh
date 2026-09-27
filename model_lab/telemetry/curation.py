"""Evaluation candidate curation, role assignment, and dataset efficiency metrics.

Provides audited transitions for candidate approval into benchmark roles, candidate
rejections, candidate queries with live lifecycle states, and telemetry intake data
efficiency tracking. Never touches or mutates the frozen core benchmark suite.
"""

from __future__ import annotations

from typing import Any

from model_lab.errors import ValidationError
from model_lab.storage.evidence import CANDIDATE_ROLES, EvidenceStore

ALLOWED_ROLES = frozenset(CANDIDATE_ROLES)


def approve(
    evidence: EvidenceStore,
    candidate_id: str,
    role: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Approve a validated candidate into an evaluation role (VALIDATED -> APPROVED -> role)."""
    if role not in ALLOWED_ROLES:
        raise ValidationError(f"invalid candidate role: {role!r}; expected one of {sorted(ALLOWED_ROLES)}")

    current_state = evidence.state("evaluation_candidate", candidate_id)
    if current_state != "VALIDATED":
        raise ValidationError(f"candidate {candidate_id} is in state {current_state!r}; approval requires VALIDATED")

    # Transitions VALIDATED -> APPROVED -> role atomically-in-sequence
    evidence.transition("evaluation_candidate", candidate_id, "APPROVED", actor=actor, reason=reason)
    return evidence.transition("evaluation_candidate", candidate_id, role, actor=actor, reason=f"assigned role {role}")


def reject(
    evidence: EvidenceStore,
    candidate_id: str,
    *,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    """Reject an evaluation candidate from NEW, VALIDATED, or APPROVED."""
    return evidence.transition("evaluation_candidate", candidate_id, "REJECTED", actor=actor, reason=reason)


def list_candidates(
    evidence: EvidenceStore,
    state: str | None = None,
) -> list[dict[str, Any]]:
    """List evaluation candidates augmented with their current lifecycle state."""
    raw_candidates = evidence.list("evaluation_candidates")
    current_states = evidence.states("evaluation_candidate")

    augmented = []
    for cand in raw_candidates:
        cand_dict = dict(cand)
        cand_state = current_states.get(cand_dict["candidate_id"])
        cand_dict["state"] = cand_state
        if state is None or cand_state == state:
            augmented.append(cand_dict)

    return augmented


def data_efficiency(evidence: EvidenceStore) -> dict[str, Any]:
    """Compute approved novel candidates / imported telemetry candidates."""
    imports = evidence.list("telemetry_imports")
    imported_runs = sum(imp.get("accepted", 0) for imp in imports)
    candidates = evidence.list("evaluation_candidates")
    candidates_count = len(candidates)

    current_states = evidence.states("evaluation_candidate")
    approved_states = {"APPROVED", *ALLOWED_ROLES}
    approved_count = sum(1 for c in candidates if c.get("duplicate_of") is None
                         and current_states.get(c["candidate_id"]) in approved_states)

    ratio = (approved_count / candidates_count) if candidates_count else None
    note = f"{approved_count} approved out of {candidates_count} imported candidates ({imported_runs} accepted runs)"

    return {
        "imported_runs": imported_runs,
        "imported_candidates": candidates_count,
        "approved": approved_count,
        "ratio": ratio,
        "note": note,
    }
