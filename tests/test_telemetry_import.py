"""Tests for telemetry batch intake, privacy scanning, deduplication, and lineage."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from model_lab.errors import IntegrityError
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore
from model_lab.telemetry.dedupe import exact_key, structural_signature, text_similarity
from model_lab.telemetry.importer import import_batch
from model_lab.telemetry.privacy import scan
from model_lab.telemetry.schema import TelemetryBatchError, parse_batch
from model_lab.telemetry.synthetic import generate_batch


def test_privacy_clean_batch_zero_findings() -> None:
    batch = generate_batch(seed=1, runs=200)
    result = scan(batch)
    assert result.status == "clean"
    assert result.reasons == ()
    assert result.redacted == batch


def test_privacy_detection_and_redaction() -> None:
    # 1. API / provider secrets
    res_secret = scan({"token": "sk-live-a1b2c3d4e5f6g7h8i9j0", "aws": "AKIA1234567890ABCDEF", "gh": "ghp_1234567890abcdef1234"})
    assert res_secret.status == "rejected"
    assert "secret_token" in res_secret.reasons
    assert "[REDACTED:secret_token]" in res_secret.redacted["token"]
    assert "[REDACTED:secret_token]" in res_secret.redacted["aws"]
    assert "[REDACTED:secret_token]" in res_secret.redacted["gh"]

    # 2. Authorization header & JWT
    jwt_tok = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123sig"
    res_auth = scan({"header": "Bearer secret-bearer-token-12345", "token": jwt_tok})
    assert res_auth.status == "rejected"
    assert "authorization_header" in res_auth.reasons
    assert "jwt" in res_auth.reasons
    assert "[REDACTED:authorization_header]" in res_auth.redacted["header"]
    assert "[REDACTED:jwt]" in res_auth.redacted["token"]

    # 3. PEM private key
    pem_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----"
    res_pem = scan({"key": pem_key})
    assert res_pem.status == "rejected"
    assert "private_key" in res_pem.reasons
    assert "[REDACTED:private_key]" in res_pem.redacted["key"]

    # 4. Credential dict fields
    res_cred = scan({"api_key": "my-key", "password": "pass", "normal": "ok"})
    assert res_cred.status == "rejected"
    assert "credential_field" in res_cred.reasons
    assert res_cred.redacted["api_key"] == "[REDACTED:credential_field]"
    assert res_cred.redacted["password"] == "[REDACTED:credential_field]"
    assert res_cred.redacted["normal"] == "ok"

    # 5. Email, Phone, PAN, Aadhaar, Luhn card
    res_pii = scan({
        "email": "alice@example.com",
        "phone": "+1-800-555-0199",
        "pan": "ABCDE1234F",
        "aadhaar": "1234 5678 9012",
        "card": "4532 0151 1283 0366",
    })
    assert res_pii.status == "rejected"
    for r in ("pii_email", "pii_phone", "pii_pan", "pii_aadhaar", "pii_card"):
        assert r in res_pii.reasons


def test_dedupe_exact_key_invariance() -> None:
    batch = generate_batch(seed=1, runs=1)
    parsed = parse_batch(batch)
    run = parsed.valid[0]

    # Mutate timestamps, run_id, request_id, decision_id, attempt_id
    mutated_raw: dict[str, Any] = dict(copy.deepcopy(run.raw))
    mutated_raw["run_id"] = "srun-different-id"
    mutated_raw["request_id"] = "req-different-id"
    mutated_raw["started_at"] = "2026-09-05T00:00:00Z"
    mutated_raw["completed_at"] = "2026-09-05T00:01:00Z"
    mutated_raw["session_id_hash"] = "999999999999999999999999"
    mutated_raw["decisions"][0]["decision_id"] = "dec-different-id"
    mutated_raw["attempts"][0]["attempt_id"] = "att-different-id"

    parsed_mutated = parse_batch({**batch, "runs": [mutated_raw]})
    run_mutated = parsed_mutated.valid[0]

    assert exact_key(run) == exact_key(run_mutated)


def test_dedupe_structural_signature_and_text_similarity() -> None:
    batch = generate_batch(seed=1, runs=2)
    parsed = parse_batch(batch)
    sig0 = structural_signature(parsed.valid[0])
    assert isinstance(sig0, str) and len(sig0) == 64

    # Text similarity
    assert text_similarity("hello world test", "test world hello") == 1.0
    assert 0.0 < text_similarity("hello world", "world goodbye") < 1.0
    assert text_similarity("apples bananas", "oranges grapes") == 0.0
    assert text_similarity("", "") == 1.0


def test_import_with_faults_quarantines_and_protects_secrets(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(
        seed=1,
        runs=50,
        faults={"missing_propensity": 2, "secret": 2, "bad_context": 1, "duplicate_run": 1},
    )
    batch_copy = copy.deepcopy(batch)

    res = import_batch(store, batch)

    # Immutability
    assert batch == batch_copy

    # Quarantined count == invalid + privacy-rejected (2 + 2 + 1 + 1 = 6)
    assert res.quarantined == 6
    assert res.accepted == (51 - 6)
    assert res.status == "imported"

    # Directly inspect SQLite database: secret strings must be absent from every stored record_json
    with store._lock:
        cursor = store.connection.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tables:
            rows = cursor.execute(f"SELECT * FROM {t}").fetchall()
            for row in rows:
                for col in row:
                    if isinstance(col, str):
                        assert "sk-live-" not in col, f"Secret leaked in table {t}: {col}"


def test_import_idempotency_and_integrity_error(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=10)

    res1 = import_batch(store, batch)
    assert res1.status == "imported"

    # Read row counts across tables
    def get_counts() -> dict[str, int]:
        with store._lock:
            cur = store.connection.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'").fetchall()]
            return {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}

    counts_before = get_counts()

    # Re-import same batch -> status "duplicate", row counts unchanged
    res2 = import_batch(store, batch)
    assert res2.status == "duplicate"
    assert res2.accepted == res1.accepted
    assert res2.quarantined == res1.quarantined
    assert res2.observations == res1.observations
    assert res2.candidates == res1.candidates
    assert res2.duplicates_marked == res1.duplicates_marked

    counts_after = get_counts()
    assert counts_before == counts_after

    # Same batch_id, different content -> IntegrityError
    batch_diff = generate_batch(seed=2, runs=10)
    batch_diff["batch_id"] = batch["batch_id"]
    with pytest.raises(IntegrityError, match="batch_id reused with different content"):
        import_batch(store, batch_diff)


def test_import_lineage_resolution(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=25)
    import_batch(store, batch)

    evidence = EvidenceStore(store)
    cands = evidence.list("evaluation_candidates")
    assert len(cands) > 0

    for cand in cands:
        lin = cand["lineage"]
        rec_id = lin["record_id"]
        source_run_id = lin["source_run_id"]
        tel_rec = evidence.get("telemetry_records", rec_id)
        assert tel_rec["run_id"] == source_run_id
        assert tel_rec["status"] == "accepted"


def test_import_dedupe_marks_duplicate_and_rejects(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch1 = generate_batch(seed=1, runs=5)
    import_batch(store, batch1)

    evidence = EvidenceStore(store)
    cands1 = evidence.list("evaluation_candidates")
    assert len(cands1) > 0
    first_cand = cands1[0]
    first_cand_id = first_cand["candidate_id"]

    # Re-send the exact run content under a new batch and run_id
    batch2 = generate_batch(seed=2, runs=1)
    dup_run = copy.deepcopy(batch1["runs"][0])
    dup_run["run_id"] = "srun-dup-retest-001"
    dup_run["request_id"] = "req-dup-retest-001"
    dup_run["started_at"] = "2026-09-03T12:00:00Z"
    dup_run["completed_at"] = "2026-09-03T12:00:04Z"
    dup_run["session_id_hash"] = "fedcba987654321012345678"
    for d in dup_run["decisions"]:
        d["decision_id"] = "dec-dup-retest-001"
        d["created_at"] = "2026-09-03T12:00:00Z"
    for a in dup_run["attempts"]:
        a["attempt_id"] = "att-dup-retest-001"
        a["decision_id"] = "dec-dup-retest-001"
    for t in dup_run["tool_events"]:
        t["event_id"] = "tool-dup-retest-001"
    for v in dup_run["validation_events"]:
        v["event_id"] = "val-dup-retest-001"
    for f in dup_run["feedback"]:
        f["feedback_id"] = "fb-dup-retest-001"
        f["created_at"] = "2026-09-03T12:02:00Z"

    batch2["runs"] = [dup_run]
    res2 = import_batch(store, batch2)
    assert res2.duplicates_marked >= 1

    cands2 = evidence.list("evaluation_candidates")
    dup_cand = [c for c in cands2 if c["source_run_id"] == "srun-dup-retest-001"][0]
    assert dup_cand["duplicate_of"] == first_cand_id

    # Verify transition state is REJECTED
    state = evidence.state("evaluation_candidate", dup_cand["candidate_id"])
    assert state == "REJECTED"


def test_import_from_path_and_envelope_errors(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "telemetry.db"))
    batch = generate_batch(seed=1, runs=5)
    file_path = tmp_path / "batch.json"
    file_path.write_text(json.dumps(batch), encoding="utf-8")

    # Import from Path
    res = import_batch(store, file_path)
    assert res.status == "imported"
    assert res.accepted == 5

    # Envelope error re-raises TelemetryBatchError and writes nothing
    bad_batch = {"schema": "InvalidTelemetry"}
    with pytest.raises(TelemetryBatchError):
        import_batch(store, bad_batch)


def test_novelty_history_excludes_the_batch_being_scored_and_candidates_stay_selective(tmp_path):
    from model_lab.storage import SQLiteStore
    from model_lab.storage.evidence import EvidenceStore
    from model_lab.telemetry.importer import import_batch
    from model_lab.telemetry.synthetic import generate_batch

    store = SQLiteStore(tmp_path / "novelty.sqlite3")
    result = import_batch(store, generate_batch(seed=31, runs=600))
    candidates = EvidenceStore(store).list("evaluation_candidates")
    first = min(candidates, key=lambda c: c["source_run_id"])
    assert first["source_run_id"].endswith("-00000")  # first run of an empty store is novel
    assert first["novelty"]["components"]["feature_distance"] == 1.0
    assert first["novelty"]["components"]["domain_rarity"] == 1.0
    assert 0 < result.candidates < result.accepted * 0.5  # high-information subset, not every run
