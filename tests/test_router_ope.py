"""tests/test_router_ope.py"""


from model_lab.telemetry.synthetic import generate_batch
from model_lab.optimization.router.off_policy import evaluate, on_policy_value
from model_lab.optimization.router.policies import LinUCBPolicy, cheapest
from model_lab.optimization.router.dataset import build_dataset
from model_lab.optimization.router.linucb import fit
from model_lab.optimization.router.features import feature_schema

from tests.test_router_bandit import _build_test_data

def test_ope_evaluates_candidates():
    # Generate 3000 examples
    obs, rews = _build_test_data(seed=5, runs=3000)
    
    f_schema = feature_schema()
    
    dataset = build_dataset(
        obs, rews,
        feature_schema_version=f_schema["feature_schema_version"],
        reward_schema_version="test-reward-v1",
        seed=5,
        split=(1.0, 0.0, 0.0), source={}
    )
    
    examples = dataset.examples_for("train")
    actions = dataset.metadata["actions"]
    
    # Train candidate
    model = fit(
        examples,
        actions=actions,
        dimension=f_schema["dimension"],
        alpha=0.5,
        lambda_=1.0,
        epsilon=0.0
    )
    cand_policy = LinUCBPolicy(model)
    
    registry = [
        {"provider": "sim", "model": "cheap", "estimated_input_cost_per_token": 0.0, "estimated_output_cost_per_token": 0.0},
        {"provider": "sim", "model": "balanced", "estimated_input_cost_per_token": 0.01, "estimated_output_cost_per_token": 0.01},
        {"provider": "sim", "model": "flagship", "estimated_input_cost_per_token": 0.1, "estimated_output_cost_per_token": 0.1},
    ]
    
    cheap_policy = cheapest(registry)
    
    rep_cand = evaluate(cand_policy, examples, bootstrap=10)
    rep_cheap = evaluate(cheap_policy, examples, bootstrap=10)
    logging = on_policy_value(examples, bootstrap=10)
    
    assert rep_cand["snips"] > logging["mean"], f"Candidate SNIPS {rep_cand['snips']} not > logging {logging['mean']}"
    assert rep_cheap["snips"] < logging["mean"], f"Cheapest SNIPS {rep_cheap['snips']} not < logging {logging['mean']}"
    
    # compute true value for candidate
    # The true expected value over evaluation contexts
    from tests.test_router_bandit import _expected_reward
    true_sum = 0.0
    for ex in examples:
        action_probs = cand_policy.probabilities(ex)
        v = sum(p * _expected_reward(ex["context"], a) for a, p in action_probs.items())
        true_sum += v
    true_val = true_sum / len(examples)
    
    assert abs(rep_cand["snips"] - true_val) < 0.05, f"SNIPS {rep_cand['snips']} not within 0.05 of true {true_val}"

def test_deterministic_logging_yields_warnings():
    # deterministic logging policy (epsilon=0)
    b_det = generate_batch(seed=6, runs=200, epsilon=0.0)
    
    obs = []
    rews = {}
    
    for r in b_det["runs"]:
        run_id = r["run_id"]
        ctx = r["routing_context"]
        dec = r["decisions"][0]
        
        obs.append({
            "observation_id": dec["decision_id"],
            "run_id": run_id,
            "import_id": "test-import",
            "context": ctx,
            "features": r["routing_context"], # dummy, we won't use it
            "eligible_actions": list(dec["eligible_models"]),
            "action": dec["selected_provider"] + "/" + dec["selected_model"],
            "propensity": dec["selection_probability"],
            "exploration": dec["exploration"],
            "shadow": False,
            "tier": r["tier"],
            "task_domain": r["task_domain"],
            "session_id_hash": None,
            "feature_schema_version": "v1",
            "policy_version": "v1",
            "group_key": None
        })
        rews[run_id] = 1.0 # dummy
    
    registry = [
        {"provider": "sim", "model": "cheap", "estimated_input_cost_per_token": 0.0, "estimated_output_cost_per_token": 0.0},
        {"provider": "sim", "model": "balanced", "estimated_input_cost_per_token": 0.01, "estimated_output_cost_per_token": 0.01},
        {"provider": "sim", "model": "flagship", "estimated_input_cost_per_token": 0.1, "estimated_output_cost_per_token": 0.1},
    ]
                
    cheap_policy = cheapest(registry)
    
    # modify one chosen action so we are definitely off-policy
    obs[0]["action"] = "sim/flagship" # force something
    
    for ex in obs:
        ex["reward"] = 1.0
        ex["features"] = [0.0]*34
        
    rep = evaluate(cheap_policy, obs, bootstrap=2)
    
    assert rep["reliable"] is False
    assert any("insufficient_support" in w or "unsupported_actions" in w for w in rep["warnings"])
