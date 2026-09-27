"""Single source of truth for every versioned contract Parakh reads or writes.

Bump a version whenever the meaning of stored/exported data changes. Records
carry these identifiers so old evidence stays interpretable after upgrades.
Cross-repo contracts (Karmi) are published as JSON Schema under ``contracts/``.
"""

from __future__ import annotations

TELEMETRY_SCHEMA = "TelemetryBatchV1"
TELEMETRY_SCHEMA_VERSION = "1.0.0"
CASE_SCHEMA_VERSION = "model_lab.case/v1"
CANDIDATE_CASE_SCHEMA_VERSION = "model_lab.candidate_case/v1"
FEATURE_SCHEMA_VERSION = "routing-features.v1"
REWARD_SCHEMA_VERSION = "reward.v1"
TRAJECTORY_GRADE_SCHEMA_VERSION = "trajectory-grade.v1"
ROUTER_DATASET_SCHEMA_VERSION = "router-dataset.v1"
ROUTER_MODEL_SCHEMA_VERSION = "linucb.v1"
PREFERENCE_SCHEMA_VERSION = "preference-pair.v1"
HARNESS_SCHEMA_VERSION = "harness-prompt.v1"
VERIFICATION_SCHEMA_VERSION = "verification-report.v1"
ARTIFACT_SCHEMA = "PolicyBundleV1"
ARTIFACT_SCHEMA_VERSION = "1.0.0"
MINIMUM_KARMI_VERSION = "0.1.0"

ALL = {
    "telemetry": f"{TELEMETRY_SCHEMA}@{TELEMETRY_SCHEMA_VERSION}",
    "case": CASE_SCHEMA_VERSION,
    "candidate_case": CANDIDATE_CASE_SCHEMA_VERSION,
    "features": FEATURE_SCHEMA_VERSION,
    "reward": REWARD_SCHEMA_VERSION,
    "trajectory_grade": TRAJECTORY_GRADE_SCHEMA_VERSION,
    "router_dataset": ROUTER_DATASET_SCHEMA_VERSION,
    "router_model": ROUTER_MODEL_SCHEMA_VERSION,
    "preference": PREFERENCE_SCHEMA_VERSION,
    "harness": HARNESS_SCHEMA_VERSION,
    "verification": VERIFICATION_SCHEMA_VERSION,
    "artifact": f"{ARTIFACT_SCHEMA}@{ARTIFACT_SCHEMA_VERSION}",
}
