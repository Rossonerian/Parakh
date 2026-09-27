"""Idempotent telemetry batch intake with quarantine, lineage, and observation extraction.

Strictly parses TelemetryBatchV1 envelopes, quarantines invalid or privacy-rejected
runs without data coercion, stores router observations and trajectories for accepted
runs, builds evaluation candidates, and idempotently records import provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from model_lab.errors import IntegrityError
from model_lab.optimization.router.features import extract
from model_lab.schemas import stable_hash, to_dict
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore
from model_lab.telemetry.candidate_builder import build_and_store_candidate
from model_lab.telemetry.novelty import NoveltyContext, score
from model_lab.telemetry.privacy import scan
from model_lab.telemetry.schema import RunRecord, batch_checksum, parse_batch


@dataclass(frozen=True)
class ImportResult:
    import_id: str
    batch_id: str
    status: str
    accepted: int
    quarantined: int
    observations: int
    candidates: int
    duplicates_marked: int


def _clean_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for k, v in event.items():
        if not isinstance(v, str):
            cleaned[k] = v
        elif k.endswith("_id") or k == "id" or k.endswith("_name") or k == "name" or "error" in k or k in (
            "validator", "status", "currency", "provider", "model",
        ):
            cleaned[k] = v
    return cleaned


def import_batch(
    store: SQLiteStore,
    batch: Mapping[str, Any] | str | Path,
    *,
    source_label: str = "karmi",
) -> ImportResult:
    """Import a TelemetryBatchV1 document into the EvidenceStore."""
    if isinstance(batch, Path):
        with open(batch, "r", encoding="utf-8") as f:
            raw_batch: Mapping[str, Any] = json.load(f)
    elif isinstance(batch, str):
        if batch.strip().startswith("{"):
            raw_batch = json.loads(batch)
        else:
            with open(batch, "r", encoding="utf-8") as f:
                raw_batch = json.load(f)
    else:
        raw_batch = batch

    # Envelope validation: re-raises TelemetryBatchError on invalid envelope
    parsed = parse_batch(raw_batch)

    evidence = EvidenceStore(store)
    checksum = batch_checksum(raw_batch)
    import_id = f"imp-{checksum[:24]}"

    # Check for existing imports with this batch_id
    existing_imports = evidence.list("telemetry_imports", batch_id=parsed.batch_id)
    if existing_imports:
        existing = existing_imports[0]
        if existing.get("batch_checksum") == checksum:
            return ImportResult(
                import_id=existing.get("import_id", import_id),
                batch_id=parsed.batch_id,
                status="duplicate",
                accepted=existing.get("accepted", 0),
                quarantined=existing.get("quarantined", 0),
                observations=existing.get("observations", 0),
                candidates=existing.get("candidates", 0),
                duplicates_marked=existing.get("duplicates_marked", 0),
            )
        raise IntegrityError("batch_id reused with different content")

    raw_runs = raw_batch.get("runs", [])
    invalid_by_index = {inv.index: inv for inv in parsed.invalid}
    valid_by_index: dict[int, RunRecord] = {}

    # Map parsed valid runs back to their original index in raw_runs
    curr_valid_idx = 0
    for i in range(len(raw_runs)):
        if i not in invalid_by_index:
            if curr_valid_idx < len(parsed.valid):
                valid_by_index[i] = parsed.valid[curr_valid_idx]
                curr_valid_idx += 1

    quarantined_count = 0
    accepted_runs: list[tuple[int, str, RunRecord]] = []

    # a) per run: telemetry_records record_id f"{import_id}:{index:06d}"
    for index, raw_run in enumerate(raw_runs):
        record_id = f"{import_id}:{index:06d}"
        run_sha256 = stable_hash(raw_run)

        if index in invalid_by_index:
            inv = invalid_by_index[index]
            priv_res = scan(raw_run)
            reasons = list(inv.reasons)
            if priv_res.status == "rejected":
                privacy_status = "rejected"
                reasons.extend(priv_res.reasons)
                record = priv_res.redacted
            else:
                privacy_status = "clean"
                record = raw_run

            reasons_sorted = sorted(dict.fromkeys(reasons))
            evidence.append(
                "telemetry_records",
                record_id,
                {
                    "import_id": import_id,
                    "run_id": inv.run_id,
                    "index": index,
                    "status": "quarantined",
                    "privacy_status": privacy_status,
                    "reasons": reasons_sorted,
                    "raw_sha256": run_sha256,
                    "record": record,
                },
            )
            quarantined_count += 1
        else:
            run_rec = valid_by_index[index]
            priv_res = scan(raw_run)
            if priv_res.status == "rejected":
                privacy_status = "rejected"
                reasons_sorted = sorted(dict.fromkeys(priv_res.reasons))
                evidence.append(
                    "telemetry_records",
                    record_id,
                    {
                        "import_id": import_id,
                        "run_id": run_rec.run_id,
                        "index": index,
                        "status": "quarantined",
                        "privacy_status": privacy_status,
                        "reasons": reasons_sorted,
                        "raw_sha256": run_sha256,
                        "record": priv_res.redacted,
                    },
                )
                quarantined_count += 1
            else:
                evidence.append(
                    "telemetry_records",
                    record_id,
                    {
                        "import_id": import_id,
                        "run_id": run_rec.run_id,
                        "index": index,
                        "status": "accepted",
                        "privacy_status": "clean",
                        "reasons": [],
                        "raw_sha256": run_sha256,
                        "record": raw_run,
                    },
                )
                accepted_runs.append((index, record_id, run_rec))

    # b) accepted runs: router_observations
    observation_count = 0
    for _, record_id, run_rec in accepted_runs:
        features_list = list(extract(run_rec.routing_context))
        for dec in (run_rec.live_decision, *run_rec.shadow_decisions):
            obs_id = f"obs-{dec.decision_id}"
            obs_row = {
                "observation_id": obs_id,
                "import_id": import_id,
                "record_id": record_id,
                "run_id": run_rec.run_id,
                "decision_id": dec.decision_id,
                "policy_version": dec.policy_version,
                "feature_schema_version": dec.feature_schema_version,
                "context": dict(run_rec.routing_context),
                "features": features_list,
                "eligible_actions": list(dec.eligible_models),
                "chosen_action": dec.action,
                "propensity": float(dec.selection_probability),
                "exploration": bool(dec.exploration),
                "shadow": bool(dec.shadow),
                "tier": run_rec.tier,
                "task_domain": run_rec.task_domain,
                "session_id_hash": run_rec.session_id_hash,
                "observed_at": dec.created_at,
            }
            evidence.append("router_observations", obs_id, obs_row)
            observation_count += 1

    # c) accepted runs: trajectories and trajectory_steps
    for _, record_id, run_rec in accepted_runs:
        traj_id = f"traj-{run_rec.run_id}"
        routing_ctx_id = f"obs-{run_rec.live_decision.decision_id}"
        traj_row = {
            "trajectory_id": traj_id,
            "run_id": run_rec.run_id,
            "import_id": import_id,
            "record_id": record_id,
            "source": "karmi_telemetry",
            "task_domain": run_rec.task_domain,
            "tier": run_rec.tier,
            "routing_context_id": routing_ctx_id,
            "policy_version": run_rec.policy_version,
            "harness_version": run_rec.harness_version,
            "prompt_version": run_rec.prompt_version,
            "final_outcome": dict(run_rec.outcome),
        }
        evidence.append("trajectories", traj_id, traj_row)

        step_idx = 0
        for att in run_rec.attempts:
            provider = att.get("provider")
            model = att.get("model")
            action = f"{provider}/{model}" if provider and model else str(model or "")
            step_id = f"{traj_id}:{step_idx:04d}"
            evidence.append(
                "trajectory_steps",
                step_id,
                {
                    "trajectory_id": traj_id,
                    "index": step_idx,
                    "step_type": "model_attempt",
                    "action": action,
                    "metadata": _clean_metadata(att),
                    "validation_result": att.get("success"),
                    "latency_ms": att.get("latency_ms"),
                    "cost": att.get("estimated_cost"),
                },
            )
            step_idx += 1

        for te in run_rec.tool_events:
            step_id = f"{traj_id}:{step_idx:04d}"
            evidence.append(
                "trajectory_steps",
                step_id,
                {
                    "trajectory_id": traj_id,
                    "index": step_idx,
                    "step_type": "tool_call",
                    "action": te.get("tool_name", ""),
                    "metadata": _clean_metadata(te),
                    "validation_result": te.get("execution_success"),
                    "latency_ms": te.get("latency_ms"),
                    "cost": te.get("cost"),
                },
            )
            step_idx += 1

        for ve in run_rec.validation_events:
            step_id = f"{traj_id}:{step_idx:04d}"
            evidence.append(
                "trajectory_steps",
                step_id,
                {
                    "trajectory_id": traj_id,
                    "index": step_idx,
                    "step_type": "validation",
                    "action": ve.get("validator", ""),
                    "metadata": _clean_metadata(ve),
                    "validation_result": ve.get("passed"),
                    "latency_ms": ve.get("latency_ms"),
                    "cost": ve.get("cost"),
                },
            )
            step_idx += 1

    # d) candidates via candidate_builder
    novelty_ctx = NoveltyContext.from_store(evidence)
    novelty_ctx.register_model_catalog(parsed.model_registry)
    session_candidates: list[dict[str, Any]] = []
    candidate_count = 0
    duplicates_marked = 0

    for _, record_id, run_rec in accepted_runs:
        nov = score(run_rec, novelty_ctx)
        cand = build_and_store_candidate(
            evidence,
            run_rec,
            import_id=import_id,
            record_id=record_id,
            batch_id=parsed.batch_id,
            producer_repo=parsed.producer_repo,
            producer_version=parsed.producer_version,
            novelty=nov,
            session_candidates=session_candidates,
        )
        if cand is not None:
            session_candidates.append(cand)
            candidate_count += 1
            if cand.get("duplicate_of") is not None:
                duplicates_marked += 1

    # e) Finally write telemetry_imports record LAST
    model_reg_list = [to_dict(m) for m in parsed.model_registry]
    imports_row = {
        "import_id": import_id,
        "batch_id": parsed.batch_id,
        "batch_checksum": checksum,
        "producer_repo": parsed.producer_repo,
        "producer_version": parsed.producer_version,
        "schema_version": parsed.schema_version,
        "feature_schema_version": parsed.feature_schema_version,
        "generated_at": parsed.generated_at,
        "window": dict(parsed.window),
        "source_label": source_label,
        "record_count": len(raw_runs),
        "accepted": len(accepted_runs),
        "quarantined": quarantined_count,
        "observations": observation_count,
        "candidates": candidate_count,
        "duplicates_marked": duplicates_marked,
        "model_registry": model_reg_list,
    }
    evidence.append("telemetry_imports", import_id, imports_row)

    return ImportResult(
        import_id=import_id,
        batch_id=parsed.batch_id,
        status="imported",
        accepted=len(accepted_runs),
        quarantined=quarantined_count,
        observations=observation_count,
        candidates=candidate_count,
        duplicates_marked=duplicates_marked,
    )
