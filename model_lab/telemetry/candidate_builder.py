"""Evaluation candidate creation and transition management from accepted telemetry runs.

Builds evaluation_candidates records for runs meeting novelty, failure, or correction
criteria, links lineage to raw telemetry_records, establishes deduplication relationships,
and executes audited lifecycle transitions (NEW -> VALIDATED or REJECTED).
"""

from __future__ import annotations

from typing import Any, Mapping

from model_lab.schema_registry import CANDIDATE_CASE_SCHEMA_VERSION
from model_lab.schemas import stable_hash, utc_now
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.dedupe import exact_key, structural_signature
from model_lab.telemetry.novelty import Novelty
from model_lab.telemetry.schema import RunRecord

DEFAULT_NOVELTY_THRESHOLD = 0.35

OUTCOME_SKETCH_FIELDS = (
    "completed",
    "first_shot_success",
    "structured_output_valid",
    "tool_success",
    "retry_count",
    "user_retry_signal",
    "user_abandon_signal",
    "user_accept_signal",
    "user_correction_signal",
    "correction_distance",
    "final_latency_ms",
    "final_cost",
    "currency",
    "critical_failure",
)


def should_create_candidate(run: RunRecord, novelty: Novelty, threshold: float = DEFAULT_NOVELTY_THRESHOLD) -> bool:
    """Determine whether an accepted run qualifies as an evaluation candidate."""
    outcome = run.outcome if isinstance(run.outcome, Mapping) else {}
    if novelty.score >= threshold:
        return True
    if outcome.get("completed") is False:
        return True
    if outcome.get("critical_failure") is True:
        return True
    if outcome.get("user_correction_signal") is True:
        return True
    return False


def _sanitize_case(run: RunRecord) -> dict[str, Any]:
    """Produce a sanitized case sketch with strictly NO free text."""
    outcome_raw = run.outcome if isinstance(run.outcome, Mapping) else {}
    outcome_sketch = {k: outcome_raw[k] for k in OUTCOME_SKETCH_FIELDS if k in outcome_raw}

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

    completed = outcome_raw.get("completed")
    failure_sig = (sorted(errors), bool(completed) if completed is not None else None)

    return {
        "routing_context": dict(run.routing_context),
        "task_domain": run.task_domain,
        "tier": run.tier,
        "live_action": run.live_decision.action,
        "eligible_actions": list(run.live_decision.eligible_models),
        "outcome": outcome_sketch,
        "tool_names": tool_names,
        "failure_signature": failure_sig,
    }


def build_and_store_candidate(
    evidence: EvidenceStore,
    run: RunRecord,
    *,
    import_id: str,
    record_id: str,
    batch_id: str,
    producer_repo: str,
    producer_version: str,
    novelty: Novelty,
    threshold: float = DEFAULT_NOVELTY_THRESHOLD,
    session_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build, append, and transition an evaluation candidate if the run qualifies."""
    if not should_create_candidate(run, novelty, threshold):
        return None

    run_exact = exact_key(run)
    run_struct = structural_signature(run)
    cand_id = "cand-" + stable_hash({"run": run.run_id, "import": import_id})[:20]

    # Find duplicate_of and similar_to across existing store candidates and current session
    duplicate_of: str | None = None
    similar_to: list[str] = []

    # Check session candidates first (earlier in this import)
    candidates_to_check: list[dict[str, Any]] = list(session_candidates or [])

    # Check store candidates with same structural signature
    try:
        existing_with_sig = evidence.list("evaluation_candidates", structural_signature=run_struct)
        candidates_to_check.extend(existing_with_sig)
    except Exception:
        pass

    # Check all store candidates if duplicate not found yet
    try:
        all_store_cands = evidence.list("evaluation_candidates")
    except Exception:
        all_store_cands = []

    seen_ids: set[str] = set()
    all_combined = []
    for c in (*candidates_to_check, *all_store_cands):
        c_id = c.get("candidate_id")
        if c_id and c_id != cand_id and c_id not in seen_ids:
            seen_ids.add(c_id)
            all_combined.append(c)

    for c in all_combined:
        c_id = c["candidate_id"]
        if duplicate_of is None and c.get("exact_key") == run_exact:
            duplicate_of = c_id
        if c.get("structural_signature") == run_struct and c_id != duplicate_of and c_id not in similar_to:
            similar_to.append(c_id)

    similar_to = similar_to[:5]

    decision_ids = [d.decision_id for d in (run.live_decision, *run.shadow_decisions)]
    lineage = {
        "batch_id": batch_id,
        "import_id": import_id,
        "record_id": record_id,
        "source_run_id": run.run_id,
        "decision_ids": decision_ids,
        "producer_repo": producer_repo,
        "producer_version": producer_version,
    }

    candidate_record = {
        "candidate_id": cand_id,
        "import_id": import_id,
        "source_run_id": run.run_id,
        "record_id": record_id,
        "origin": "karmi_telemetry",
        "dataset_role": "telemetry_candidate",
        "schema_version": CANDIDATE_CASE_SCHEMA_VERSION,
        "created_at": utc_now(),
        "novelty_score": novelty.score,
        "novelty": {
            "score": novelty.score,
            "components": dict(novelty.components),
            "reasons": list(novelty.reasons),
        },
        "exact_key": run_exact,
        "structural_signature": run_struct,
        "duplicate_of": duplicate_of,
        "similar_to": similar_to,
        "privacy_status": "clean",
        "case": _sanitize_case(run),
        "lineage": lineage,
    }

    # Append to evaluation_candidates
    evidence.append("evaluation_candidates", cand_id, candidate_record)

    # Lifecycle transitions: NEW -> VALIDATED or REJECTED
    evidence.transition("evaluation_candidate", cand_id, "NEW", actor="importer", reason="telemetry import")
    if duplicate_of is None:
        evidence.transition("evaluation_candidate", cand_id, "VALIDATED", actor="importer", reason="schema+privacy validated")
    else:
        evidence.transition("evaluation_candidate", cand_id, "REJECTED", actor="importer", reason=f"exact duplicate of {duplicate_of}")

    return candidate_record
