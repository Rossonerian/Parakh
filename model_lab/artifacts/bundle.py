"""PolicyBundleV1: immutable, checksummed, signed, provenance-complete export.

Only an APPROVED policy candidate with a passing verification report can be
exported, and exporting moves it to EXPORTED (Parakh's terminal state). The
bundle is a directory of canonical JSON files; ``checksums.json`` lists the
sha256 of every other file and ``signature.sig`` is an Ed25519 signature over
the exact bytes of ``checksums.json``. Rendering is a pure function of stored
evidence, so ``rerender`` must reproduce every byte (the reproducibility gate).
Parakh never writes Karmi state: the manifest only *recommends* shadow mode.
No pickle or executable content is ever written.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from model_lab.artifacts import ed25519, signer
from model_lab.artifacts.provenance import build_provenance, missing_fields
from model_lab.errors import IntegrityError, ValidationError
from model_lab.optimization.harness import HarnessCandidate, PromptRegistry
from model_lab.optimization.harness import bundle_files as harness_bundle_files
from model_lab.schema_registry import ARTIFACT_SCHEMA, ARTIFACT_SCHEMA_VERSION, MINIMUM_KARMI_VERSION
from model_lab.storage.evidence import EvidenceStore
from model_lab.verifier import registry_for_imports

CHECKSUMS = "checksums.json"
SIGNATURE = "signature.sig"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _latest_passing_report(evidence: EvidenceStore, candidate_id: str) -> dict[str, Any]:
    reports = [r for r in evidence.list("verification_reports", policy_candidate_id=candidate_id) if r.get("passed") is True]
    if not reports:
        raise IntegrityError(f"{candidate_id} has no passing verification report")
    return reports[-1]


def _eligibility(dataset_examples: Iterable[Mapping[str, Any]], registry: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tiers: dict[str, set[str]] = {}
    for example in dataset_examples:
        tiers.setdefault(example["tier"], set()).update(example["eligible_actions"])
    return {"authority": "karmi", "note": "Descriptive only: eligibility observed in training telemetry. Karmi's eligibility engine is "
                                           "authoritative and must filter candidates before this policy scores them.",
            "observed_eligible_actions_by_tier": {tier: sorted(actions) for tier, actions in sorted(tiers.items())},
            "model_registry": [dict(m) for m in registry]}


def render(evidence: EvidenceStore, candidate_id: str, *, secret: bytes, git: Mapping[str, Any], artifact_version: str,
           previous_compatible_version: str | None = None) -> dict[str, bytes]:
    """All bundle files as bytes. Pure given the stored evidence, key, git state and version."""
    candidate = evidence.get("policy_candidates", candidate_id)
    if candidate.get("kind") != "router":
        raise ValidationError("only router policy candidates can be exported as PolicyBundleV1")
    report = _latest_passing_report(evidence, candidate_id)
    training = evidence.get("policy_training_runs", candidate["training_id"])
    dataset = evidence.get("datasets", candidate["dataset_id"])
    examples = [row["example"] for row in evidence.list("dataset_examples", dataset_id=candidate["dataset_id"])]
    registry = registry_for_imports(evidence, (dataset.get("metadata", {}).get("source") or {}).get("import_ids", []))
    approved = [h for h in evidence.history("policy_candidate", candidate_id) if h["to_state"] == "APPROVED"]
    if not approved or evidence.state("policy_candidate", candidate_id) not in ("APPROVED", "EXPORTED"):
        raise IntegrityError(f"{candidate_id} is not APPROVED")
    harness_id = report.get("harness_candidate_id")
    provenance = build_provenance(
        git=git, training=training, dataset=dataset, feature_schema=candidate["feature_schema"],
        reward={"schema_version": dataset["metadata"].get("reward_schema_version"), "config_hashes": dataset["metadata"].get("reward_config_hashes", [])},
        model_registry=list(registry), grader_versions=report.get("grader_versions", {}),
        evaluation_run_ids=report.get("evaluation_run_ids", []), human_review_run_ids=report.get("human_review_run_ids", []),
        verification_report_id=report["report_id"], harness_candidate_id=harness_id)
    missing = missing_fields(provenance)
    if missing:
        raise IntegrityError(f"provenance incomplete: {', '.join(missing)}")
    files: dict[str, bytes] = {
        "routing_policy.json": canonical(candidate["policy"]),
        "feature_schema.json": canonical(candidate["feature_schema"]),
        "eligibility_constraints.json": canonical(_eligibility(examples, registry)),
        "evaluation.json": canonical({k: report[k] for k in sorted(report) if k != "created_at"}),
        "provenance.json": canonical(provenance),
    }
    if harness_id:
        harness = HarnessCandidate.from_record(evidence.get("policy_candidates", harness_id))
        if evidence.state("policy_candidate", harness_id) != "VERIFIED":
            raise IntegrityError(f"harness candidate {harness_id} is not VERIFIED")
        for name, document in sorted(harness_bundle_files(harness, PromptRegistry(evidence)).items()):
            files[f"harness/{name}"] = canonical(document)
    public = signer.key_id(ed25519.public_key(secret))
    manifest = {
        "schema": ARTIFACT_SCHEMA, "schema_version": ARTIFACT_SCHEMA_VERSION, "artifact_version": artifact_version,
        "policy_schema_version": candidate["policy"]["policy_schema_version"], "feature_schema_version": candidate["feature_schema"]["feature_schema_version"],
        "feature_schema_id": candidate["feature_schema"]["schema_id"], "algorithm": candidate["policy"]["algorithm"],
        "minimum_karmi_version": MINIMUM_KARMI_VERSION, "previous_compatible_version": previous_compatible_version,
        "model_registry": [{"action": f"{m['provider']}/{m['model']}", "provider": m["provider"], "model": m["model"],
                            "model_version": m.get("model_version")} for m in registry],
        "evaluation_run_ids": list(report.get("evaluation_run_ids", [])), "created_at": approved[-1]["created_at"],
        "policy_candidate_id": candidate_id, "evidence_class": report.get("evidence_class", "SIMULATED"),
        "signing_key_id": public, "files": sorted([*files, "manifest.json"]), "parakh_status": "EXPORTED",
        "recommended_karmi_mode": "shadow",
    }
    files["manifest.json"] = canonical(manifest)
    checksums = canonical({"algorithm": "sha256", "files": {name: _sha256(data) for name, data in sorted(files.items())}})
    files[CHECKSUMS] = checksums
    files[SIGNATURE] = canonical(signer.sign(secret, checksums, signed_file=CHECKSUMS))
    return files


def next_version(evidence: EvidenceStore, created_at: str) -> str:
    day = created_at[:10].replace("-", ".")
    same_day = [m for m in evidence.list("artifact_manifests") if m["bundle_version"].startswith(f"policy-{day}.")]
    return f"policy-{day}.{len(same_day) + 1}"


def export(evidence: EvidenceStore, candidate_id: str, *, out_root: str | Path, secret: bytes, git: Mapping[str, Any],
           actor: str, previous_compatible_version: str | None = None) -> dict[str, Any]:
    """Render, write read-only files, record the manifest, move the candidate to EXPORTED."""
    if evidence.state("policy_candidate", candidate_id) != "APPROVED":
        raise IntegrityError(f"{candidate_id} must be APPROVED to export (currently {evidence.state('policy_candidate', candidate_id)})")
    approved_at = [h for h in evidence.history("policy_candidate", candidate_id) if h["to_state"] == "APPROVED"][-1]["created_at"]
    version = next_version(evidence, approved_at)
    files = render(evidence, candidate_id, secret=secret, git=git, artifact_version=version,
                   previous_compatible_version=previous_compatible_version)
    target = Path(out_root) / version
    if target.exists():
        raise IntegrityError(f"bundle {target} already exists; bundles are immutable")
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.chmod(path, 0o444)
    checksums = json.loads(files[CHECKSUMS])
    record = {"bundle_id": version, "bundle_version": version, "policy_candidate_id": candidate_id, "path": str(target),
              "checksums_sha256": _sha256(files[CHECKSUMS]), "files": checksums["files"],
              "signature": json.loads(files[SIGNATURE]), "git": dict(git), "previous_compatible_version": previous_compatible_version}
    evidence.append("artifact_manifests", version, record)
    evidence.transition("policy_candidate", candidate_id, "EXPORTED", actor=actor, reason=f"exported {version}",
                        details={"bundle": version, "path": str(target)})
    return record


def verify(path: str | Path, trusted_public_keys: Iterable[str]) -> list[str]:
    """Parakh-side bundle check: trusted signature, exact file set and contained checksums."""
    root = Path(path)
    if (root / CHECKSUMS).is_symlink() or (root / SIGNATURE).is_symlink():
        return ["symlink in bundle metadata"]
    errors: list[str] = []
    try:
        checksums_bytes = (root / CHECKSUMS).read_bytes()
        signature = json.loads((root / SIGNATURE).read_text(encoding="utf-8"))
        checksums = json.loads(checksums_bytes)
    except (OSError, ValueError) as exc:
        return [f"unreadable bundle: {exc}"]
    if not isinstance(signature, dict) or not isinstance(checksums, dict):
        return ["invalid bundle metadata"]
    errors.extend(signer.verify(signature, checksums_bytes, trusted_public_keys))
    files = checksums.get("files")
    if not isinstance(files, dict) or any(not isinstance(name, str) or not isinstance(digest, str)
                                           for name, digest in files.items()):
        return errors + ["invalid checksum file list"]
    entries = list(root.rglob("*"))
    errors.extend(f"symlink in bundle: {p.relative_to(root)}" for p in entries if p.is_symlink())
    present = {str(p.relative_to(root)) for p in entries if p.is_file()} - {CHECKSUMS, SIGNATURE}
    errors.extend(f"unlisted file {name}" for name in sorted(present - files.keys()))
    errors.extend(f"missing listed file {name}" for name in sorted(files.keys() - present))
    resolved_root = root.resolve()
    for name, digest in sorted(files.items()):
        part = Path(name)
        if not name or "\\" in name or part.is_absolute() or ".." in part.parts or not (root / part).resolve().is_relative_to(resolved_root):
            errors.append(f"unsafe bundle path {name}")
            continue
        file = root / part
        if file.is_symlink():
            continue
        if not file.is_file():
            errors.append(f"missing file {name}")
        elif _sha256(file.read_bytes()) != digest:
            errors.append(f"checksum mismatch {name}")
    return errors


def rerender_matches(evidence: EvidenceStore, bundle_record: Mapping[str, Any], *, secret: bytes) -> list[str]:
    """Reproducibility: re-render from evidence and compare every byte with the written bundle."""
    root = Path(bundle_record["path"])
    files = render(evidence, bundle_record["policy_candidate_id"], secret=secret, git=bundle_record["git"],
                   artifact_version=bundle_record["bundle_version"], previous_compatible_version=bundle_record.get("previous_compatible_version"))
    return [f"not reproducible: {name}" for name, data in sorted(files.items()) if (root / name).read_bytes() != data]
