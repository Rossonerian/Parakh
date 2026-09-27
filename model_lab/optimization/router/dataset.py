"""Router dataset generation and persistence.

Builds static datasets for router training and off-policy evaluation, applying exclusions,
lineage-aware splits, and checksums to ensure reproducibility.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from model_lab.errors import IntegrityError, ValidationError
from model_lab.schemas import stable_hash
from model_lab.schema_registry import ROUTER_DATASET_SCHEMA_VERSION

@dataclass(frozen=True)
class RouterDataset:
    dataset_id: str
    checksum: str
    examples: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]

    def examples_for(self, split: str) -> tuple[dict[str, Any], ...]:
        if split not in ("train", "validation"):
            raise ValueError(f"Use sealed_holdout for test split, not examples_for({split!r})")
        return tuple(ex for ex in self.examples if ex["split"] == split)

    def sealed_holdout(self, purpose: str) -> tuple[dict[str, Any], ...]:
        if purpose != "verification":
            raise IntegrityError("sealed holdout can only be accessed for verification")
        return tuple(ex for ex in self.examples if ex["split"] == "test")


def build_dataset(
    observations: Sequence[Mapping[str, Any]],
    rewards: Mapping[str, Mapping[str, Any]],
    *,
    feature_schema_version: str,
    reward_schema_version: str,
    seed: int,
    split: tuple[float, float, float] = (0.7, 0.15, 0.15),
    min_propensity: float = 0.0,
    source: dict[str, Any],
) -> RouterDataset:
    if len(split) != 3 or not abs(sum(split) - 1.0) < 1e-6:
        raise ValueError("split must be a 3-tuple summing to 1.0")
    
    train_frac = split[0]
    val_frac = split[0] + split[1]

    exclusions: dict[str, int] = {
        "shadow_decision_not_executed": 0,
        "invalid_propensity": 0,
        "below_min_propensity": 0,
        "action_not_eligible": 0,
        "feature_schema_mismatch": 0,
        "no_reward": 0,
        "reward_schema_mismatch": 0,
    }

    examples_list = []
    actions_set = set()
    policy_versions = set()
    reward_config_hashes = set()
    groups_by_split: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}

    for obs in observations:
        obs_id = obs["observation_id"]
        run_id = obs["run_id"]
        
        if obs.get("shadow", False):
            exclusions["shadow_decision_not_executed"] += 1
            continue

        prop = obs.get("propensity")
        if prop is None or prop <= 0 or prop > 1:
            exclusions["invalid_propensity"] += 1
            continue
        
        if prop < min_propensity:
            exclusions["below_min_propensity"] += 1
            continue

        chosen = obs["chosen_action"]
        eligible = obs["eligible_actions"]
        if chosen not in eligible:
            exclusions["action_not_eligible"] += 1
            continue

        if obs.get("feature_schema_version") != feature_schema_version or len(obs.get("features", [])) != 34:
            exclusions["feature_schema_mismatch"] += 1
            continue

        if run_id not in rewards:
            exclusions["no_reward"] += 1
            continue
            
        rew = rewards[run_id]
        if rew.get("schema_version") != reward_schema_version:
            exclusions["reward_schema_mismatch"] += 1
            continue
            
        scalar = rew.get("scalar")
        if scalar is None:
            reason = rew.get("excluded_reason", "unknown")
            k = f"reward_excluded:{reason}"
            exclusions[k] = exclusions.get(k, 0) + 1
            continue

        group_key = obs.get("group_key") or obs.get("session_id_hash") or run_id
        bucket = int(stable_hash({"group": group_key, "seed": seed})[:8], 16) % 1000
        frac = bucket / 1000.0
        
        if frac < train_frac:
            split_name = "train"
        elif frac < val_frac:
            split_name = "validation"
        else:
            split_name = "test"

        groups_by_split[split_name].add(group_key)

        comp = rew.get("components", {})
        cost_raw = comp.get("cost_raw")
        currency = comp.get("currency")
        cost = cost_raw if currency == "USD" else None
        
        actions_set.add(chosen)
        policy_versions.add(obs.get("policy_version"))
        if "config_hash" in rew:
            reward_config_hashes.add(rew["config_hash"])

        examples_list.append({
            "observation_id": obs_id,
            "run_id": run_id,
            "split": split_name,
            "features": obs["features"],
            "context": obs["context"],
            "eligible_actions": eligible,
            "action": chosen,
            "propensity": prop,
            "reward": scalar,
            "tier": obs.get("tier"),
            "task_domain": obs.get("task_domain"),
            "policy_version": obs.get("policy_version"),
            "success": comp.get("task_completed"),
            "cost": cost,
            "latency_ms": comp.get("latency_ms"),
            "critical": comp.get("safety_violation"),
            "tool_failure_penalty": comp.get("tool_failure_penalty")
        })

    examples_list.sort(key=lambda x: x["observation_id"])
    examples = tuple(examples_list)
    checksum = stable_hash(examples)
    dataset_id = "ds-" + checksum[:20]

    counts_by_split = {
        "train": sum(1 for e in examples if e["split"] == "train"),
        "validation": sum(1 for e in examples if e["split"] == "validation"),
        "test": sum(1 for e in examples if e["split"] == "test"),
    }
    
    # groups_by_split needs to be lists to be JSON serializable
    groups_by_split_list = {k: sorted(list(v)) for k, v in groups_by_split.items()}

    metadata = {
        "schema_version": ROUTER_DATASET_SCHEMA_VERSION,
        "feature_schema_version": feature_schema_version,
        "reward_schema_version": reward_schema_version,
        "reward_config_hashes": sorted(list(reward_config_hashes)),
        "seed": seed,
        "split_fractions": split,
        "counts_by_split": counts_by_split,
        "exclusions": {k: v for k, v in exclusions.items() if v > 0},
        "policy_versions": sorted(list(policy_versions)),
        "source": source,
        "sampling_rules": (
            "Lineage-aware split using group_key/session_id_hash/run_id. "
            "Exclusions applied for shadow, missing/invalid propensity, "
            "schema mismatches, missing/excluded rewards, and eligible action mismatches."
        ),
        "actions": sorted(list(actions_set)),
        "groups_by_split": groups_by_split_list,
    }

    return RouterDataset(
        dataset_id=dataset_id,
        checksum=checksum,
        examples=examples,
        metadata=metadata
    )


def persist_dataset(evidence, dataset: RouterDataset) -> None:
    evidence.append("datasets", dataset.dataset_id, {
        "dataset_id": dataset.dataset_id,
        "kind": "router",
        "checksum": dataset.checksum,
        "metadata": dataset.metadata,
    })
    
    for i, example in enumerate(dataset.examples):
        record_id = f"{dataset.dataset_id}:{i:06d}"
        evidence.append("dataset_examples", record_id, {
            "dataset_id": dataset.dataset_id,
            "split": example["split"],
            "observation_id": example["observation_id"],
            "example": example
        })


def load_dataset(evidence, dataset_id: str) -> RouterDataset:
    ds_record = evidence.get("datasets", dataset_id)
    if not ds_record:
        raise ValidationError(f"Dataset {dataset_id} not found")
        
    checksum = ds_record["checksum"]
    metadata = ds_record["metadata"]
    
    examples = []
    # Using list to query dataset_examples
    examples_records = evidence.list("dataset_examples", dataset_id=dataset_id)
    # The list is unordered in general, we should sort by observation_id or the suffix
    examples_records.sort(key=lambda r: r["observation_id"])
    
    for record in examples_records:
        examples.append(record["example"])
        
    examples_tuple = tuple(examples)
    loaded_checksum = stable_hash(examples_tuple)
    if loaded_checksum != checksum:
        raise IntegrityError("Dataset checksum mismatch")
        
    return RouterDataset(
        dataset_id=dataset_id,
        checksum=checksum,
        examples=examples_tuple,
        metadata=metadata
    )
