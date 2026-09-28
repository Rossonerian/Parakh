"""Export of approved preference pairs and DPO/PEFT readiness evaluation.

Filters and exports approved preference datasets in JSONL format,
and checks gate criteria for downstream alignment training.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from model_lab.schemas import stable_json
from model_lab.storage.evidence import EvidenceStore

SPEC_FIELDS = (
    "pair_id",
    "prompt_or_context_ref",
    "chosen",
    "rejected",
    "confidence",
    "reason",
    "source_run_id",
    "approval_state",
)


def export_approved(evidence: EvidenceStore, path: str | Path) -> int:
    """Export all APPROVED preference pairs to a JSONL file sorted by pair_id.

    Returns the number of exported pairs.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_pairs = evidence.list("preference_pairs")
    states = evidence.states("preference_pair")

    approved_rows: list[dict[str, Any]] = []
    for pair in all_pairs:
        pair_id = pair["pair_id"]
        current_state = states.get(pair_id, pair.get("approval_state"))
        if current_state == "APPROVED":
            row = {field: pair.get(field) for field in SPEC_FIELDS}
            row["approval_state"] = "APPROVED"
            approved_rows.append(row)

    approved_rows.sort(key=lambda r: r["pair_id"])

    with open(out_path, "w", encoding="utf-8") as f:
        for row in approved_rows:
            f.write(stable_json(row) + "\n")

    return len(approved_rows)


def readiness(
    evidence: EvidenceStore,
    *,
    min_pairs: int = 500,
    trainable_target: str | None = None,
) -> dict[str, Any]:
    """Evaluate whether the preference dataset satisfies criteria for DPO/PEFT alignment."""
    all_pairs = evidence.list("preference_pairs")
    states = evidence.states("preference_pair")

    counts_by_state: dict[str, int] = {}
    counts_by_category: dict[str, int] = {}
    approved_count = 0

    for pair in all_pairs:
        pair_id = str(pair["pair_id"])
        raw_state = states.get(pair_id) if pair_id in states else pair.get("approval_state", "UNKNOWN")
        state = str(raw_state or "UNKNOWN")
        category = str(pair.get("category") or "unknown")

        counts_by_state[state] = counts_by_state.get(state, 0) + 1
        counts_by_category[category] = counts_by_category.get(category, 0) + 1

        if state == "APPROVED":
            approved_count += 1

    has_trainable_target = bool(trainable_target and str(trainable_target).strip())
    reasons: list[str] = []

    if approved_count < min_pairs:
        reasons.append(f"approved_count_{approved_count}_below_minimum_{min_pairs}")
    if not has_trainable_target:
        reasons.append("missing_trainable_target")

    justified = (approved_count >= min_pairs) and has_trainable_target

    return {
        "counts_by_state": counts_by_state,
        "counts_by_category": counts_by_category,
        "approved_count": approved_count,
        "has_trainable_target": has_trainable_target,
        "trainable_target": trainable_target,
        "justified": justified,
        "reasons": reasons,
    }
