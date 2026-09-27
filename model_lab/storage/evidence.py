"""Append-only optimization evidence on the same SQLite file as runs/attempts.

Every kind of record lives in its own table ``(record_id, created_at,
<indexed columns>, record_json)`` protected by UPDATE/DELETE triggers. Mutable
lifecycle state (candidate approval, preference approval, policy promotion) is
never an UPDATE: it is an appended row in ``state_transitions`` validated
against the state machines below, so every promotion is auditable.

Writes are idempotent: re-appending an identical record is a no-op; appending
a different record under an existing ID is an ``IntegrityError``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Mapping

from model_lab.errors import IntegrityError, NotFoundError, ValidationError
from model_lab.schemas import stable_json, utc_now
from model_lab.storage.sqlite import SQLiteStore

# kind -> indexed columns (all TEXT/REAL affinity; values also live in record_json)
KINDS: dict[str, tuple[str, ...]] = {
    "telemetry_imports": ("batch_id", "batch_checksum", "producer_repo"),
    "telemetry_records": ("import_id", "run_id", "status", "privacy_status"),
    "evaluation_candidates": ("import_id", "source_run_id", "structural_signature", "privacy_status"),
    "trajectories": ("run_id", "import_id", "task_domain", "tier"),
    "trajectory_steps": ("trajectory_id", "step_type"),
    "trajectory_grades": ("trajectory_id", "schema_version"),
    "router_observations": ("run_id", "import_id", "chosen_action", "shadow", "feature_schema_version"),
    "rewards": ("subject_type", "subject_id", "schema_version"),
    "datasets": ("kind", "checksum"),
    "dataset_examples": ("dataset_id", "split", "observation_id"),
    "preference_pairs": ("source_run_id", "category"),
    "policy_training_runs": ("dataset_id", "algorithm"),
    "policy_candidates": ("kind", "parent_id", "training_id"),
    "ope_reports": ("policy_candidate_id", "dataset_id"),
    "verification_reports": ("policy_candidate_id", "passed"),
    "harness_prompts": ("component", "parent_id"),
    "harness_evaluations": ("prompt_id", "split"),
    "artifact_manifests": ("policy_candidate_id", "bundle_version"),
}

# Lifecycle state machines: entity kind -> allowed (from, to) edges. ``None`` = initial.
CANDIDATE_ROLES = ("TRAIN_ONLY", "REGRESSION", "VALIDATION", "HOLDOUT", "ADVERSARIAL")
STATE_MACHINES: dict[str, set[tuple[str | None, str]]] = {
    "evaluation_candidate": {
        (None, "NEW"), ("NEW", "VALIDATED"), ("NEW", "REJECTED"), ("VALIDATED", "REJECTED"),
        ("VALIDATED", "APPROVED"), ("APPROVED", "REJECTED"),
        *(("APPROVED", role) for role in CANDIDATE_ROLES),
    },
    "preference_pair": {
        (None, "PROPOSED"), (None, "NEEDS_REVIEW"), (None, "EXCLUDED"),
        ("NEEDS_REVIEW", "PROPOSED"), ("NEEDS_REVIEW", "EXCLUDED"),
        ("PROPOSED", "APPROVED"), ("PROPOSED", "REJECTED"), ("APPROVED", "REJECTED"),
    },
    "policy_candidate": {
        (None, "DRAFT"), ("DRAFT", "TRAINED"), ("TRAINED", "VERIFIED"), ("TRAINED", "REJECTED"),
        ("VERIFIED", "APPROVED"), ("VERIFIED", "REJECTED"), ("APPROVED", "EXPORTED"), ("APPROVED", "REJECTED"),
    },
}
# Roles are terminal assignments; re-assigning a role requires a new candidate record.
TERMINAL_STATES = {"REJECTED", "EXPORTED", "EXCLUDED", *CANDIDATE_ROLES}


def _ddl() -> str:
    statements = []
    for kind, columns in KINDS.items():
        cols = "".join(f", {c}" for c in columns)
        statements.append(f"CREATE TABLE IF NOT EXISTS {kind} (record_id TEXT PRIMARY KEY, created_at TEXT NOT NULL{cols}, record_json TEXT NOT NULL);")
        for c in columns:
            statements.append(f"CREATE INDEX IF NOT EXISTS ix_{kind}_{c} ON {kind}({c});")
    statements.append("""CREATE TABLE IF NOT EXISTS state_transitions (
        transition_id INTEGER PRIMARY KEY AUTOINCREMENT, entity_kind TEXT NOT NULL, entity_id TEXT NOT NULL,
        from_state TEXT, to_state TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
        record_json TEXT NOT NULL);""")
    statements.append("CREATE INDEX IF NOT EXISTS ix_transitions_entity ON state_transitions(entity_kind, entity_id, transition_id);")
    for table in (*KINDS, "state_transitions"):
        for op in ("UPDATE", "DELETE"):
            statements.append(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END;")
    return "\n".join(statements)


class EvidenceStore:
    """Typed-by-kind JSON evidence over an open ``SQLiteStore`` connection."""

    def __init__(self, store: SQLiteStore, *, ensure_schema: bool = True) -> None:
        """``ensure_schema=False`` is for readers (e.g. console polling): no DDL, so no write lock."""
        self.store = store
        self.connection: sqlite3.Connection = store.connection
        if ensure_schema:
            with store._lock:
                self.connection.executescript(_ddl())

    def has_schema(self) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'state_transitions'").fetchone() is not None

    @staticmethod
    def _kind(kind: str) -> tuple[str, ...]:
        if kind not in KINDS:
            raise ValidationError(f"unknown evidence kind: {kind}")
        return KINDS[kind]

    def append(self, kind: str, record_id: str, record: Mapping[str, Any], *, created_at: str | None = None) -> bool:
        """Insert once. Returns True if inserted, False if the identical record already exists."""
        columns = self._kind(kind)
        if not isinstance(record_id, str) or not record_id:
            raise ValidationError("record_id must be non-empty text")
        payload = stable_json(record)
        values = [_column_value(record.get(c)) for c in columns]
        with self.store._lock:
            existing = self.connection.execute(f"SELECT record_json FROM {kind} WHERE record_id = ?", (record_id,)).fetchone()
            if existing is not None:
                if existing[0] != payload:
                    raise IntegrityError(f"{kind} {record_id} already exists with different content")
                return False
            placeholders = ", ".join("?" for _ in range(len(columns) + 3))
            self.connection.execute(
                f"INSERT INTO {kind} (record_id, created_at{''.join(', ' + c for c in columns)}, record_json) VALUES ({placeholders})",
                (record_id, created_at or utc_now(), *values, payload),
            )
        return True

    def get(self, kind: str, record_id: str) -> dict[str, Any]:
        self._kind(kind)
        with self.store._lock:
            row = self.connection.execute(f"SELECT record_json FROM {kind} WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"unknown {kind} record: {record_id}")
        return json.loads(row[0])

    def exists(self, kind: str, record_id: str) -> bool:
        self._kind(kind)
        with self.store._lock:
            return self.connection.execute(f"SELECT 1 FROM {kind} WHERE record_id = ?", (record_id,)).fetchone() is not None

    def list(self, kind: str, **filters: Any) -> list[dict[str, Any]]:
        """Records in insertion order, filtered by equality on indexed columns."""
        columns = self._kind(kind)
        unknown = set(filters) - set(columns)
        if unknown:
            raise ValidationError(f"{kind} cannot be filtered by {sorted(unknown)}")
        where = " AND ".join(f"{c} = ?" for c in filters) or "1 = 1"
        with self.store._lock:
            rows = self.connection.execute(f"SELECT record_json FROM {kind} WHERE {where} ORDER BY rowid",
                                           tuple(_column_value(v) for v in filters.values())).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count(self, kind: str, **filters: Any) -> int:
        return len(self.list(kind, **filters))

    # ------------------------------------------------------------------ lifecycle
    def state(self, entity_kind: str, entity_id: str) -> str | None:
        with self.store._lock:
            row = self.connection.execute(
                "SELECT to_state FROM state_transitions WHERE entity_kind = ? AND entity_id = ? ORDER BY transition_id DESC LIMIT 1",
                (entity_kind, entity_id)).fetchone()
        return row[0] if row else None

    def history(self, entity_kind: str, entity_id: str) -> list[dict[str, Any]]:
        with self.store._lock:
            rows = self.connection.execute(
                "SELECT record_json FROM state_transitions WHERE entity_kind = ? AND entity_id = ? ORDER BY transition_id",
                (entity_kind, entity_id)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def states(self, entity_kind: str) -> dict[str, str]:
        """Current state of every entity of a kind."""
        with self.store._lock:
            rows = self.connection.execute(
                "SELECT entity_id, to_state FROM state_transitions WHERE transition_id IN "
                "(SELECT MAX(transition_id) FROM state_transitions WHERE entity_kind = ? GROUP BY entity_id)", (entity_kind,)).fetchall()
        return {r[0]: r[1] for r in rows}

    def transition(self, entity_kind: str, entity_id: str, to_state: str, *, actor: str, reason: str,
                   details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Append a lifecycle transition after checking the state machine (atomic)."""
        machine = STATE_MACHINES.get(entity_kind)
        if machine is None:
            raise ValidationError(f"no state machine for {entity_kind}")
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValidationError("transitions require a named actor and a reason")
        with self.store._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                current = self.state(entity_kind, entity_id)
                if (current, to_state) not in machine:
                    raise IntegrityError(f"{entity_kind} {entity_id}: transition {current} -> {to_state} is not allowed")
                record = {"entity_kind": entity_kind, "entity_id": entity_id, "from_state": current, "to_state": to_state,
                          "actor": actor, "reason": reason, "details": dict(details or {}), "created_at": utc_now()}
                self.connection.execute(
                    "INSERT INTO state_transitions(entity_kind, entity_id, from_state, to_state, actor, reason, created_at, record_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (entity_kind, entity_id, current, to_state, actor, reason, record["created_at"], stable_json(record)))
                self.connection.execute("COMMIT")
            except BaseException:
                self.connection.execute("ROLLBACK")
                raise
        return record


def _column_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, (int, float, str)):
        return value
    return stable_json(value)


def records_by_id(records: Iterable[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {r[key]: r for r in records}
