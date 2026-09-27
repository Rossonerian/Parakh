"""tests/test_router_bandit.py"""

import pytest
from typing import Any

from model_lab.telemetry.synthetic import generate_batch, expected_outcome, static_policy
from model_lab.telemetry.schema import action_id
from model_lab.optimization.router.dataset import build_dataset
from model_lab.optimization.router.features import extract, feature_schema
from model_lab.optimization.router.linucb import fit, to_policy_document, from_policy_document
from model_lab.optimization.router.trainer import train_candidate, reproduce
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore
from model_lab.errors import ValidationError

def _compute_reward(outcome: dict[str, Any]) -> float:
    completed = 1.0 if outcome.get("completed") else 0.0
    cost = float(outcome.get("final_cost", 0.0))
    latency = float(outcome.get("final_latency_ms", 0.0))
    
    return completed - 0.2 * min(cost / 0.01, 1.5) - 0.1 * min(latency / 8000.0, 1.5)


def _expected_reward(ctx: dict[str, Any], action: str) -> float:
    eo = expected_outcome(ctx, action)
    completed = eo["success_probability"]
    cost = eo["cost"]
    latency = eo["latency_ms"]
    return completed - 0.2 * min(cost / 0.01, 1.5) - 0.1 * min(latency / 8000.0, 1.5)


def _build_test_data(seed: int, runs: int):
    b = generate_batch(seed=seed, runs=runs, epsilon=0.5)
    observations = []
    rewards = {}
    f_schema = feature_schema()
    
    for r in b["runs"]:
        run_id = r["run_id"]
        ctx = r["routing_context"]
        dec = r["decisions"][0]
        action = action_id(dec["selected_provider"], dec["selected_model"])
        eligible = list(dec["eligible_models"])
        
        obs = {
            "observation_id": dec["decision_id"],
            "run_id": run_id,
            "import_id": "test-import",
            "context": ctx,
            "features": extract(ctx, f_schema),
            "eligible_actions": eligible,
            "chosen_action": action,
            "propensity": dec["selection_probability"],
            "exploration": dec["exploration"],
            "shadow": dec.get("shadow", False),
            "tier": r["tier"],
            "task_domain": r["task_domain"],
            "session_id_hash": r.get("session_id_hash"),
            "feature_schema_version": f_schema["feature_schema_version"],
            "policy_version": dec["policy_version"],
            "group_key": None
        }
        observations.append(obs)
        
        outcome = r.get("outcome", {})
        rew_scalar = _compute_reward(outcome)
        
        rewards[run_id] = {
            "scalar": rew_scalar,
            "confidence": 1.0,
            "excluded_reason": None,
            "schema_version": "test-reward-v1",
            "config_hash": "testhash",
            "components": {
                "task_completed": outcome.get("completed", False),
                "cost_raw": outcome.get("final_cost", 0.0),
                "currency": outcome.get("currency", "USD"),
                "latency_ms": outcome.get("final_latency_ms", 0.0),
                "safety_violation": outcome.get("critical_failure", False),
                "tool_failure_penalty": 0.0
            }
        }
    return observations, rewards

def test_bandit_agreement_improves():
    f_schema = feature_schema()
    
    # 400 fresh contexts
    b_test = generate_batch(seed=999, runs=400, epsilon=0.0)
    test_cases = []
    for r in b_test["runs"]:
        ctx = r["routing_context"]
        eligible = list(r["decisions"][0]["eligible_models"])
        
        # optimal action
        best_action = max(eligible, key=lambda a: _expected_reward(ctx, a))
        static_action = static_policy(ctx, eligible)
        test_cases.append({
            "context": ctx,
            "features": extract(ctx, f_schema),
            "eligible_actions": eligible,
            "best": best_action,
            "static": static_action
        })
        
    def train_and_eval(n_runs: int) -> int:
        obs, rews = _build_test_data(seed=42, runs=n_runs)
        dataset = build_dataset(
            obs, rews,
            feature_schema_version=f_schema["feature_schema_version"],
            reward_schema_version="test-reward-v1",
            seed=42,
            split=(1.0, 0.0, 0.0), source={} # all train
        )
        model = fit(
            dataset.examples_for("train"),
            actions=dataset.metadata["actions"],
            dimension=f_schema["dimension"],
            alpha=0.5,
            lambda_=1.0,
            epsilon=0.0
        )
        
        match_count = 0
        for tc in test_cases:
            pred = model.greedy(tc["features"], tc["eligible_actions"])
            if pred == tc["best"]:
                match_count += 1
        return match_count

    match_300 = train_and_eval(300)
    match_4000 = train_and_eval(4000)
    
    static_match = sum(1 for tc in test_cases if tc["static"] == tc["best"])
    
    assert match_4000 > match_300, f"Agreement did not improve: 300->{match_300}, 4000->{match_4000}"
    assert match_4000 > static_match, f"Did not exceed static: 4000->{match_4000}, static->{static_match}"

def test_probabilities_sum_and_eligible():
    obs, rews = _build_test_data(seed=1, runs=100)
    f_schema = feature_schema()
    dataset = build_dataset(
        obs, rews,
        feature_schema_version=f_schema["feature_schema_version"],
        reward_schema_version="test-reward-v1",
        seed=1,
        split=(1.0, 0.0, 0.0), source={}
    )
    
    model = fit(
        dataset.examples_for("train"),
        actions=dataset.metadata["actions"],
        dimension=f_schema["dimension"],
        alpha=0.5,
        lambda_=1.0,
        epsilon=0.1
    )
    
    # adversarial properties
    # we can modify theta to be adversarial
    import copy
    adv_params = copy.deepcopy(model.parameters)
    for a in adv_params:
        adv_params[a]["theta"] = [1e6] * f_schema["dimension"]
        adv_params[a]["a_inv"][0][0] = 1e6
        
    model = copy.replace(model, parameters=adv_params) # wait, dataclasses.replace is in dataclasses
    from dataclasses import replace
    model = replace(model, parameters=adv_params)
    
    import random
    rng = random.Random(2)
    actions = list(dataset.metadata["actions"])
    
    for _ in range(50):
        # random eligible subset
        eligible = random.sample(actions, k=rng.randint(1, len(actions)))
        x = [rng.random() for _ in range(f_schema["dimension"])]
        
        probs = model.probabilities(x, eligible)
        assert abs(sum(probs.values()) - 1.0) < 1e-6
        for a in probs:
            assert a in eligible

def test_determinism_and_reproduce(tmp_path):
    obs, rews = _build_test_data(seed=3, runs=200)
    f_schema = feature_schema()
    dataset = build_dataset(
        obs, rews,
        feature_schema_version=f_schema["feature_schema_version"],
        reward_schema_version="test-reward-v1",
        seed=3,
        split=(0.7, 0.15, 0.15), source={}
    )
    
    store = EvidenceStore(SQLiteStore(str(tmp_path / "ev.db")))
    # append dataset first, since reproduce loads it
    from model_lab.optimization.router.dataset import persist_dataset
    persist_dataset(store, dataset)
    
    hyper = {"alpha": 0.1, "lambda_": 0.5, "epsilon": 0.05}
    
    cand_id1, model1 = train_candidate(store, dataset, hyperparameters=hyper, seed=3, git={})
    cand_id2, model2 = train_candidate(store, dataset, hyperparameters=hyper, seed=3, git={})
    
    assert cand_id1 == cand_id2
    
    # test reproduce()
    from model_lab.schemas import stable_hash
    from model_lab.schema_registry import ROUTER_MODEL_SCHEMA_VERSION
    training_id = "train-" + stable_hash({
        "dataset_checksum": dataset.checksum,
        "hyperparameters": hyper,
        "seed": 3,
        "code_version": ROUTER_MODEL_SCHEMA_VERSION
    })[:20]
    
    rep = reproduce(store, training_id)
    assert rep["reproducible"] is True
    assert rep["parameters_checksum_match"] is True
    
    doc = to_policy_document(model1)
    model3 = from_policy_document(doc)
    
    for i in range(100):
        x = [i*0.01] * f_schema["dimension"]
        eligible = list(dataset.metadata["actions"])
        p1 = model1.probabilities(x, eligible)
        p3 = model3.probabilities(x, eligible)
        
        assert set(p1.keys()) == set(p3.keys())
        for k in p1:
            assert abs(p1[k] - p3[k]) < 1e-9

def test_dataset_exclusions_and_splits():
    obs, rews = _build_test_data(seed=4, runs=20)
    
    # inject shadow
    obs[0]["shadow"] = True
    # bad propensity
    obs[1]["propensity"] = -0.1
    obs[2]["propensity"] = 1.1
    # missing reward
    del rews[obs[3]["run_id"]]
    # eligible mismatch
    obs[4]["chosen_action"] = "not_in_eligible"
    
    f_schema = feature_schema()
    dataset = build_dataset(
        obs, rews,
        feature_schema_version=f_schema["feature_schema_version"],
        reward_schema_version="test-reward-v1",
        seed=4,
        split=(0.5, 0.25, 0.25), source={}
    )
    
    excl = dataset.metadata["exclusions"]
    assert excl.get("shadow_decision_not_executed", 0) >= 1
    assert excl.get("invalid_propensity", 0) >= 2
    assert excl.get("no_reward", 0) >= 1
    assert excl.get("action_not_eligible", 0) >= 1
    
    # check sealed holdout raises
    from model_lab.errors import IntegrityError
    with pytest.raises(IntegrityError):
        dataset.sealed_holdout("wrong")
        
    holdout = dataset.sealed_holdout("verification")
    assert all(e["split"] == "test" for e in holdout)
    
    # groups never span splits
    group_splits = {}
    for ex in dataset.examples:
        # for our generated data, run_id is the group_key
        g = ex["run_id"]
        if g not in group_splits:
            group_splits[g] = ex["split"]
        else:
            assert group_splits[g] == ex["split"]


@pytest.mark.parametrize("epsilon", [-0.1, 1.1, float("nan")])
def test_invalid_exploration_probability_is_rejected(epsilon):
    with pytest.raises(ValidationError, match="exploration"):
        fit([], actions=["sim/cheap"], dimension=1, epsilon=epsilon)
    model = fit([], actions=["sim/cheap"], dimension=1, epsilon=0.05)
    document = to_policy_document(model)
    document["exploration"]["epsilon"] = epsilon
    with pytest.raises(ValidationError, match="exploration"):
        from_policy_document(document)
