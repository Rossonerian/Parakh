"""provenance.json for PolicyBundleV1: everything needed to reproduce a candidate.

``missing_fields`` is a hard verifier gate: a bundle whose provenance lacks any
required field (or whose git tree was dirty) is not exportable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from model_lab import __version__
from model_lab.datasets import CORE_SUITE_SHA256, CORE_SUITE_VERSION

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FIELDS = (
    "parakh_git_commit", "git_dirty", "parakh_version", "benchmark_versions", "telemetry_dataset", "feature_schema",
    "reward_schema", "algorithm", "hyperparameters", "random_seeds", "provider_model_versions", "grader_versions",
    "evaluation_run_ids", "human_review_run_ids", "training_id", "verification_report_id", "python_version",
)


def git_state(repo: str | Path = ROOT) -> dict[str, Any]:
    """Current commit and whether tracked files differ from it (untracked files ignored)."""
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain", "--untracked-files=no")),
                "branch": run("rev-parse", "--abbrev-ref", "HEAD")}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "branch": None}


def build_provenance(*, git: Mapping[str, Any], training: Mapping[str, Any], dataset: Mapping[str, Any],
                     feature_schema: Mapping[str, Any], reward: Mapping[str, Any], model_registry: list[Mapping[str, Any]],
                     grader_versions: Mapping[str, str], evaluation_run_ids: list[str], human_review_run_ids: list[str],
                     verification_report_id: str, harness_candidate_id: str | None = None) -> dict[str, Any]:
    return {
        "parakh_git_commit": git.get("commit"), "git_dirty": git.get("dirty"), "git_branch": git.get("branch"),
        "parakh_version": __version__, "python_version": ".".join(map(str, sys.version_info[:3])),
        "benchmark_versions": {"core": {"version": CORE_SUITE_VERSION, "sha256": CORE_SUITE_SHA256}},
        "telemetry_dataset": {"dataset_id": dataset.get("dataset_id"), "checksum": dataset.get("checksum"),
                              "schema_version": dataset.get("metadata", {}).get("schema_version"),
                              "source": dataset.get("metadata", {}).get("source")},
        "feature_schema": {"version": feature_schema.get("feature_schema_version"), "schema_id": feature_schema.get("schema_id")},
        "reward_schema": {"version": reward.get("schema_version"), "config_hashes": list(reward.get("config_hashes", []))},
        "algorithm": training.get("algorithm"), "hyperparameters": training.get("hyperparameters"),
        "random_seeds": {"training": training.get("seed"), "dataset_split": dataset.get("metadata", {}).get("seed")},
        "training_id": training.get("training_id"), "code_version": training.get("code_version"),
        "provider_model_versions": [{"action": f"{m['provider']}/{m['model']}", "model_version": m.get("model_version")} for m in model_registry],
        "grader_versions": dict(grader_versions), "evaluation_run_ids": list(evaluation_run_ids),
        "human_review_run_ids": list(human_review_run_ids), "verification_report_id": verification_report_id,
        "harness_candidate_id": harness_candidate_id,
    }


def missing_fields(provenance: Mapping[str, Any]) -> list[str]:
    """Required fields that are absent/None, plus a dirty/unknown git state (not reproducible)."""
    missing = [f for f in REQUIRED_FIELDS if provenance.get(f) is None]
    if provenance.get("git_dirty") is not False and "git_dirty" not in missing:
        missing.append("git_dirty (tree must be clean and known)")
    return missing
