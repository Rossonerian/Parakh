"""policies.py: Router policy wrappers and baselines.

Provides uniform interface for evaluating various policies (LinUCB, static,
cheapest, flagship) on context examples.
"""

from typing import Any, Mapping

from model_lab.optimization.router.linucb import LinUCBModel
from model_lab.telemetry.schema import action_id

class LinUCBPolicy:
    def __init__(self, model: LinUCBModel):
        self.model = model
        self.name = "linucb"
        
    def probabilities(self, example: Mapping[str, Any]) -> dict[str, float]:
        eligible = example["eligible_actions"]
        x = example["features"]
        return self.model.probabilities(x, eligible)


class FixedPreferencePolicy:
    def __init__(self, name: str, ranking: list[str]):
        self.name = name
        self.ranking = ranking
        
    def probabilities(self, example: Mapping[str, Any]) -> dict[str, float]:
        eligible = example["eligible_actions"]
        for action in self.ranking:
            if action in eligible:
                return {action: 1.0}
        return {}


def cheapest(model_registry: list[dict[str, Any]]) -> FixedPreferencePolicy:
    actions_costs = []
    for entry in model_registry:
        cost = entry["estimated_input_cost_per_token"] + entry["estimated_output_cost_per_token"]
        a_id = action_id(entry["provider"], entry["model"])
        actions_costs.append((cost, a_id))
        
    actions_costs.sort()
    ranking = [a for cost, a in actions_costs]
    return FixedPreferencePolicy("cheapest", ranking)


def flagship(model_registry: list[dict[str, Any]]) -> FixedPreferencePolicy:
    actions_costs = []
    for entry in model_registry:
        cost = entry["estimated_input_cost_per_token"] + entry["estimated_output_cost_per_token"]
        a_id = action_id(entry["provider"], entry["model"])
        actions_costs.append((-cost, a_id))
        
    actions_costs.sort()
    ranking = [a for neg_cost, a in actions_costs]
    return FixedPreferencePolicy("flagship", ranking)
