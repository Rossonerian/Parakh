"""Dataset roles, the frozen core benchmark, and the holdout firewall.

The 60-case seed suite stays where it is (tooling depends on the path) and is
*frozen*: its SHA-256 is pinned here and checked before any optimization use.
Roles are metadata, not file moves:

* ``core``        — every seed case; the frozen regression baseline.
* ``train``       — seed split ``train``; optimizers may read these.
* ``validation``  — seed split ``calibration``; used to compare candidates.
* ``holdout``     — seed split ``holdout``; never given to an optimizer.
* ``adversarial`` — seed cases tagged adversarial/red-team (none yet) plus
  approved telemetry candidates promoted to ADVERSARIAL.
* telemetry candidates live in the evidence store, quarantined until approved.

Optimizers must obtain cases through ``optimizer_cases`` (which refuses the
holdout); only the verifier calls ``holdout_cases``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from model_lab.benchmark import load_suite
from model_lab.errors import IntegrityError, ValidationError
from model_lab.schema_registry import CASE_SCHEMA_VERSION
from model_lab.schemas import Case, Suite

ROOT = Path(__file__).resolve().parents[1]
CORE_SUITE_PATH = ROOT / "benchmarks" / "seed_cases.jsonl"
CORE_SUITE_VERSION = "0.1.0"
CORE_SUITE_SHA256 = "9f82842371ab949a1018c5625875b1830d625d95c7b7380d5e35a172f8df230e"
CORE_CREATED_AT = "2026-09-09T00:00:00+00:00"  # seed bank preparation date (README)

SPLIT_TO_ROLE = {"train": "train", "calibration": "validation", "holdout": "holdout"}
OPTIMIZER_ROLES = frozenset({"train", "validation"})
ADVERSARIAL_TAGS = frozenset({"adversarial", "red_team"})


@dataclass(frozen=True)
class CaseRecord:
    """Anti-contamination metadata every case carries (plan §3.2)."""

    case_id: str
    origin: str
    dataset_role: str
    schema_version: str
    created_at: str
    approval_state: str
    sensitive_data_status: str
    lineage: dict


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_core_suite(path: str | Path = CORE_SUITE_PATH) -> Suite:
    """Load the core suite, refusing any byte change to the frozen file."""
    digest = file_sha256(path)
    if digest != CORE_SUITE_SHA256:
        raise IntegrityError(f"core benchmark {path} changed (sha256 {digest}); core cases are frozen — add new cases as candidates instead")
    return load_suite(path)


def role_of(case: Case) -> str:
    try:
        return SPLIT_TO_ROLE[case.split]
    except KeyError as exc:
        raise ValidationError(f"case {case.case_id} has unknown split {case.split}") from exc


def core_case_records(suite: Suite) -> list[CaseRecord]:
    records = []
    for case in suite.cases:
        provenance = case.provenance
        records.append(CaseRecord(
            case_id=case.case_id, origin=provenance.origin, dataset_role=role_of(case),
            schema_version=CASE_SCHEMA_VERSION, created_at=CORE_CREATED_AT, approval_state="FROZEN",
            sensitive_data_status="real_personal_data" if provenance.real_personal_data else "synthetic_no_personal_data",
            lineage={"suite_version": suite.suite_version, "suite_sha256": CORE_SUITE_SHA256, "family_id": case.family_id},
        ))
    return records


def optimizer_cases(suite: Suite, roles: Iterable[str] = ("train",)) -> tuple[Case, ...]:
    """Cases an optimizer may see. The holdout role is structurally unavailable here."""
    wanted = set(roles)
    if not wanted <= OPTIMIZER_ROLES:
        raise IntegrityError(f"optimizers may only read {sorted(OPTIMIZER_ROLES)}; requested {sorted(wanted)}")
    return tuple(case for case in suite.cases if role_of(case) in wanted)


def holdout_cases(suite: Suite) -> tuple[Case, ...]:
    """Verifier-only accessor for the sealed holdout role."""
    return tuple(case for case in suite.cases if role_of(case) == "holdout")


def adversarial_cases(suite: Suite) -> tuple[Case, ...]:
    return tuple(case for case in suite.cases if ADVERSARIAL_TAGS & set(case.tags))
