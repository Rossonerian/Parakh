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
    train_mean_reward = sum(ex["reward"] for ex in train_examples) / train_count if train_count > 0 else 0.0
    
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
    
    parameters_checksum_match = (parameters_checksum == run["parameters_checksum"])
    
    # We should also compare candidates directly but the run has parameters_checksum.
    # To get the original policy document, we can find the candidate that points to this training_id.
    candidates = evidence.list("policy_candidates", training_id=training_id)
    if not candidates:
        # Fallback to true if we just match checksum?
        # The prompt says: compare every theta/a_inv entry within 1e-12.
        pass
        
    candidate = candidates[0] if candidates else None
    max_abs_diff = 0.0
    
    if candidate:
        orig_doc = candidate["policy"]
        for a, p in orig_doc["parameters"].items():
            if a in model.parameters:
                new_p = model.parameters[a]
                for i in range(len(p["theta"])):
                    max_abs_diff = max(max_abs_diff, abs(p["theta"][i] - new_p["theta"][i]))
                for i in range(len(p["a_inv"])):
                    for j in range(len(p["a_inv"][i])):
                        max_abs_diff = max(max_abs_diff, abs(p["a_inv"][i][j] - new_p["a_inv"][i][j]))
                        
    return {
        "reproducible": parameters_checksum_match and (max_abs_diff < 1e-12),
        "max_abs_diff": float(max_abs_diff),
        "parameters_checksum_match": parameters_checksum_match
    }
