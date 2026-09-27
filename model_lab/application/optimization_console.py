"""Operator read model and review actions for the optimization engine (console-facing).

Every call opens its own SQLite connection, so it is safe from worker threads, and reads never
create a database. Review actions are the same audited transitions the CLI uses, always with a
named actor and a reason. Nothing here trains, verifies, exports or touches Karmi.

These are operator views, separate from blind grading: they may show routing actions and
sanitized correction text, never case references, rubrics or reviewer identities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from model_lab.application.observability import open_store
from model_lab.errors import ValidationError
from model_lab.optimization.metrics import compounding_metrics
from model_lab.preferences.extractor import review as review_pair
from model_lab.storage.evidence import CANDIDATE_ROLES, EvidenceStore
from model_lab.telemetry.curation import approve as approve_candidate, reject as reject_candidate

ROLES = CANDIDATE_ROLES


@dataclass(frozen=True)
class CandidateRow:
    candidate_id: str
    state: str | None
    novelty: float | None
    novelty_reasons: tuple[str, ...]
    privacy: str | None
    domain: str | None
    tier: str | None
    live_action: str | None
    source_run_id: str | None
    import_id: str | None
    duplicate_of: str | None
    similar: int
    outcome: dict[str, Any]
    failure_signature: Any
    lineage: dict[str, Any]


@dataclass(frozen=True)
class PreferenceRow:
    pair_id: str
    state: str | None
    category: str | None
    confidence: float | None
    reason: str
    chosen: str
    rejected: str
    source_run_id: str | None


@dataclass(frozen=True)
class PolicyRow:
    candidate_id: str
    kind: str
    state: str | None
    parent_id: str | None
    dataset_id: str | None
    report: dict[str, Any] | None
    bundle: str | None


@dataclass
class OptimizationSnapshot:
    db_exists: bool
    imports: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[CandidateRow] = field(default_factory=list)
    preferences: list[PreferenceRow] = field(default_factory=list)
    policies: list[PolicyRow] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def load_optimization(data_dir: str | Path) -> OptimizationSnapshot:
    store = open_store(data_dir)
    if store is None:
        return OptimizationSnapshot(db_exists=False)
    try:
        evidence = EvidenceStore(store, ensure_schema=False)
        snap = OptimizationSnapshot(db_exists=True)
        if not evidence.has_schema():  # no optimization evidence yet (plain ModelLab workspace)
            return snap
        snap.imports = [{k: imp.get(k) for k in ("import_id", "batch_id", "producer_repo", "accepted", "quarantined", "candidates")}
                        for imp in evidence.list("telemetry_imports")]
        states = evidence.states("evaluation_candidate")
        for c in evidence.list("evaluation_candidates"):
            case = c.get("case") or {}
            snap.candidates.append(CandidateRow(
                c["candidate_id"], states.get(c["candidate_id"]), c.get("novelty_score"), tuple((c.get("novelty") or {}).get("reasons", ())),
                c.get("privacy_status"), case.get("task_domain"), case.get("tier"), case.get("live_action"), c.get("source_run_id"),
                c.get("import_id"), c.get("duplicate_of"), len(c.get("similar_to") or ()), dict(case.get("outcome") or {}),
                case.get("failure_signature"), dict(c.get("lineage") or {})))
        snap.candidates.sort(key=lambda row: (row.state != "VALIDATED", -(row.novelty or 0.0), row.candidate_id))
        pair_states = evidence.states("preference_pair")
        for p in evidence.list("preference_pairs"):
            snap.preferences.append(PreferenceRow(p["pair_id"], pair_states.get(p["pair_id"]), p.get("category"), p.get("confidence"),
                                                  str(p.get("reason", "")), str(p.get("chosen", "")), str(p.get("rejected", "")),
                                                  p.get("source_run_id")))
        snap.preferences.sort(key=lambda row: (row.state not in ("NEEDS_REVIEW", "PROPOSED"), row.pair_id))
        policy_states = evidence.states("policy_candidate")
        reports: dict[str, dict[str, Any]] = {}
        for report in evidence.list("verification_reports"):
            reports[report["policy_candidate_id"]] = report  # stored in append order: the last one wins
        bundles = {m["policy_candidate_id"]: m["bundle_version"] for m in evidence.list("artifact_manifests")}
        for c in evidence.list("policy_candidates"):
            report = reports.get(c["candidate_id"])
            summary = None if report is None else {
                "report_id": report["report_id"], "passed": report["passed"], "evidence_class": report.get("evidence_class"),
                "failed": [(g["gate"], g["reason"]) for g in report["hard_gates"] if not g["passed"]],
                "limitations": list(report.get("limitations", []))}
            snap.policies.append(PolicyRow(c["candidate_id"], c["kind"], policy_states.get(c["candidate_id"]), c.get("parent_id"),
                                           c.get("dataset_id"), summary, bundles.get(c["candidate_id"])))
        snap.metrics = compounding_metrics(evidence)
        return snap
    finally:
        store.close()


def _operator(actor: str, reason: str) -> tuple[str, str]:
    actor, reason = actor.strip(), reason.strip()
    if not actor or not reason:
        raise ValidationError("review actions need a named actor and a reason")
    return actor, reason


def review_candidate(data_dir: str | Path, candidate_id: str, decision: str, *, role: str | None, actor: str, reason: str) -> dict[str, Any]:
    actor, reason = _operator(actor, reason)
    store = open_store(data_dir)
    if store is None:
        raise ValidationError("no workspace database")
    try:
        evidence = EvidenceStore(store)
        if decision == "approve":
            if role not in CANDIDATE_ROLES:
                raise ValidationError(f"choose a role: {', '.join(CANDIDATE_ROLES)}")
            return approve_candidate(evidence, candidate_id, role, actor=actor, reason=reason)
        if decision == "reject":
            return reject_candidate(evidence, candidate_id, actor=actor, reason=reason)
        raise ValidationError(f"unknown decision {decision!r}")
    finally:
        store.close()


def review_preference(data_dir: str | Path, pair_id: str, decision: str, *, actor: str, reason: str) -> dict[str, Any]:
    actor, reason = _operator(actor, reason)
    store = open_store(data_dir)
    if store is None:
        raise ValidationError("no workspace database")
    try:
        return review_pair(EvidenceStore(store), pair_id, decision, actor=actor, reason=reason)
    finally:
        store.close()
