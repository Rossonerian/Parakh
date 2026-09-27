"""trainer.py: Router policy trainer and reproduction.

Trains LinUCB policies on datasets and records the models and their training
metadata in the evidence store.
"""

from typing import Any

from model_lab.schemas import stable_hash
from model_lab.schema_registry import ROUTER_MODEL_SCHEMA_VERSION
from model_lab.optimization.router.linucb import fit, to_policy_document
from model_lab.optimization.router.dataset import RouterDataset, load_dataset
from model_lab.optimization.router.features import feature_schema

def train_candidate(
    evidence,
    dataset: RouterDataset,
    *,
    hyperparameters: dict[str, Any],
    seed: int,
    git: dict[str, Any],
    parent_id: str | None = None
) -> tuple[str, Any]:
    
    train_examples = dataset.examples_for("train")
    
    # metrics computation
    train_count = len(train_examples)
    train_mean_reward = sum(ex["reward"] for ex in train_examples) / train_count if train_count > 0 else None
    
    # fit
    model = fit(
        train_examples,
        actions=dataset.metadata["actions"],
        dimension=feature_schema()["dimension"],
        **hyperparameters
    )
    
    policy_doc = to_policy_document(model)
    parameters_checksum = stable_hash(policy_doc)
    
    training_id = "train-" + stable_hash({
        "dataset_checksum": dataset.checksum,
        "hyperparameters": hyperparameters,
        "seed": seed,
        "code_version": ROUTER_MODEL_SCHEMA_VERSION
    })[:20]
    
    candidate_id = "pol-" + parameters_checksum[:20]
    
    per_action_counts = {a: p["n"] for a, p in model.parameters.items()}
    
    evidence.append("policy_training_runs", training_id, {
        "training_id": training_id,
        "dataset_id": dataset.dataset_id,
        "dataset_checksum": dataset.checksum,
        "algorithm": "linucb",
        "hyperparameters": hyperparameters,
        "seed": seed,
        "git": git,
        "code_version": ROUTER_MODEL_SCHEMA_VERSION,
        "parameters_checksum": parameters_checksum,
        "metrics": {
            "train_examples": train_count,
            "per_action_counts": per_action_counts,
            "train_mean_reward": train_mean_reward
        }
    })
    
    if evidence.exists("policy_candidates", candidate_id):
        return candidate_id, model
        
    evidence.append("policy_candidates", candidate_id, {
        "candidate_id": candidate_id,
        "kind": "router",
        "parent_id": parent_id,
        "training_id": training_id,
        "policy": policy_doc,
        "feature_schema": feature_schema(),
        "dataset_id": dataset.dataset_id
    })
    
    evidence.transition("policy_candidate", candidate_id, "DRAFT", actor="trainer", reason="created")
    evidence.transition("policy_candidate", candidate_id, "TRAINED", actor="trainer", reason="training complete")
    
    return candidate_id, model


def reproduce(evidence, training_id: str) -> dict[str, Any]:
    run = evidence.get("policy_training_runs", training_id)
    dataset = load_dataset(evidence, run["dataset_id"])
    
    train_examples = dataset.examples_for("train")
    model = fit(
        train_examples,
        actions=dataset.metadata["actions"],
        dimension=feature_schema()["dimension"],
        **run["hyperparameters"]
    )
    
    policy_doc = to_policy_document(model)
    parameters_checksum = stable_hash(policy_doc)
    
    parameters_checksum_match = parameters_checksum == run["parameters_checksum"]
    candidates = evidence.list("policy_candidates", training_id=training_id)
    if len(candidates) != 1:
        return {"reproducible": False, "max_abs_diff": None, "parameters_checksum_match": parameters_checksum_match}
    original = candidates[0]["policy"]
    if set(original["parameters"]) != set(model.parameters):
        return {"reproducible": False, "max_abs_diff": None, "parameters_checksum_match": parameters_checksum_match}
    max_abs_diff = 0.0
    for action, stored in original["parameters"].items():
        current = model.parameters[action]
        if len(stored["theta"]) != len(current["theta"]) or len(stored["a_inv"]) != len(current["a_inv"]):
            return {"reproducible": False, "max_abs_diff": None, "parameters_checksum_match": parameters_checksum_match}
        for x, y in zip(stored["theta"], current["theta"], strict=True):
            max_abs_diff = max(max_abs_diff, abs(x - y))
        for row_x, row_y in zip(stored["a_inv"], current["a_inv"], strict=True):
            if len(row_x) != len(row_y):
                return {"reproducible": False, "max_abs_diff": None, "parameters_checksum_match": parameters_checksum_match}
            for x, y in zip(row_x, row_y, strict=True):
                max_abs_diff = max(max_abs_diff, abs(x - y))
    return {
        "reproducible": parameters_checksum_match and max_abs_diff < 1e-12,
        "max_abs_diff": max_abs_diff,
        "parameters_checksum_match": parameters_checksum_match,
    }
