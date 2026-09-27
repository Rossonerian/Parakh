"""Exporter for optimized harness bundles (prompts and recovery policies).

Builds bundle files conforming to HARNESS_SCHEMA_VERSION with component prompt
texts, lineage tracking root-to-leaf, and recovery policies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model_lab.optimization.harness.candidate import HarnessCandidate
from model_lab.optimization.harness.prompt_registry import PromptRegistry
from model_lab.schema_registry import HARNESS_SCHEMA_VERSION
from model_lab.schemas import to_dict


def bundle_files(candidate: HarnessCandidate, registry: PromptRegistry) -> dict[str, Any]:
    """Generate the export dictionary containing prompts.json and recovery_policy.json structures."""
    components_payload: dict[str, Any] = {}
    lineage_payload: dict[str, list[str]] = {}

    for comp, prompt_id in sorted(candidate.components.items()):
        version = registry.get(prompt_id)
        components_payload[comp] = {
            "prompt_id": version.prompt_id,
            "text": version.text,
            "parent_id": version.parent_id,
            "generation_method": version.generation_method,
        }
        lineage_versions = registry.lineage(prompt_id)
        lineage_payload[comp] = [v.prompt_id for v in lineage_versions]

    prompts_data = {
        "harness_schema_version": HARNESS_SCHEMA_VERSION,
        "candidate_id": candidate.candidate_id,
        "components": components_payload,
        "lineage": lineage_payload,
    }

    recovery_policy_data = to_dict(candidate.recovery_policy)

    return {
        "prompts.json": prompts_data,
        "recovery_policy.json": recovery_policy_data,
    }


def export_bundle(
    candidate: HarnessCandidate,
    registry: PromptRegistry,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Export bundle files to a directory on disk and return their file paths."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    bundle = bundle_files(candidate, registry)

    prompts_file = out_path / "prompts.json"
    prompts_file.write_text(
        json.dumps(bundle["prompts.json"], ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    policy_file = out_path / "recovery_policy.json"
    policy_file.write_text(
        json.dumps(bundle["recovery_policy.json"], ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "prompts.json": prompts_file,
        "recovery_policy.json": policy_file,
    }
