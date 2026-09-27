"""Candidate-based harness optimization with immutable versions and train/val separation.

External Optimizers Architecture:
External prompt and harness optimizers (such as DSPy, GEPA, MIPRO, or custom evolutionary
search frameworks) plug into this pipeline cleanly by implementing the ``CandidateGenerator``
protocol. Such an external optimizer receives the parent candidate, its current component texts,
coarse failure summaries (strictly isolated from references and rubrics), and a seeded random
generator. The external generator proposes candidate changes as ``(component, new_text, method)``
tuples. All proposed candidates automatically undergo oracle-leakage filtering (via
``assert_oracle_free``), immutable content-addressed registration, append-only evidence
persistence, and multi-split evaluation without coupling the optimization algorithm to
internal storage, providers, or benchmark secrets.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from model_lab.datasets import optimizer_cases
from model_lab.errors import IntegrityError
from model_lab.optimization.harness.candidate import HarnessCandidate, assert_oracle_free
from model_lab.optimization.harness.metric_adapter import (
    HarnessEvaluation,
    evaluate,
    persist,
)
from model_lab.optimization.harness.prompt_registry import (
    DEFAULT_BASELINE_PATH,
    PromptRegistry,
)
from model_lab.providers.base import Provider
from model_lab.schemas import Suite, utc_now
from model_lab.storage.evidence import EvidenceStore


@dataclass(frozen=True)
class FailureSummary:
    """Coarse failure information provided to generators.

    Contains only case identifier, domain, evaluation method, and coarse failure
    category. Never exposes references, rubrics, or candidate answers.
    """

    case_id: str
    domain: str
    evaluation_method: str
    failure_category: str


class CandidateGenerator(Protocol):
    """Protocol for candidate harness generators and optimizers."""

    def propose(
        self,
        parent: HarnessCandidate,
        texts: Mapping[str, str],
        failures: list[FailureSummary],
        rng: random.Random,
    ) -> list[tuple[str, str, str]]:
        """Propose modifications as list of (component, new_text, generation_method)."""
        ...


INSTRUCTION_LIBRARY: dict[str, tuple[str, str]] = {
    "invalid_json": ("system", "Always respond with only valid json."),
    "json_mismatch": ("system", "Ensure output formatting matches requirements and respond with only valid json."),
    "text_mismatch": ("system", "Always respond with exact concise text."),
    "expenses": ("system", "Always calculate financial amounts accurately."),
    "document_extraction": ("system", "Always extract structured data verbatim."),
    "tabular_analysis": ("system", "Always analyze tabular structures row by row."),
    "task_planning": ("system", "Always plan and order tasks sequentially."),
    "exact_json": ("system", "Always respond with only valid json."),
    "exact_text": ("system", "Always respond with exact concise text."),
    "schema": ("system", "Always adhere strictly to the requested schema."),
}


@dataclass
class FailureDrivenGenerator:
    """Rule-based generator selecting targeted instructions from an instruction library."""

    instruction_library: dict[str, tuple[str, str]] = field(
        default_factory=lambda: dict(INSTRUCTION_LIBRARY)
    )

    def propose(
        self,
        parent: HarnessCandidate,
        texts: Mapping[str, str],
        failures: list[FailureSummary],
        rng: random.Random,
    ) -> list[tuple[str, str, str]]:
        if not failures:
            return []

        proposals: list[tuple[str, str, str]] = []
        seen_proposals: set[tuple[str, str]] = set()

        # Sort failures for determinism before examining them
        sorted_failures = sorted(failures, key=lambda f: (f.domain, f.evaluation_method, f.case_id))

        for failure in sorted_failures:
            # Check domain first, then failure category, then evaluation method
            entry = None
            if failure.domain in self.instruction_library:
                entry = self.instruction_library[failure.domain]
            elif failure.failure_category in self.instruction_library:
                entry = self.instruction_library[failure.failure_category]
            elif failure.evaluation_method in self.instruction_library:
                entry = self.instruction_library[failure.evaluation_method]

            if entry is not None:
                component, instruction = entry
                current_text = texts.get(component, "")
                if instruction.casefold() not in current_text.casefold():
                    key = (component, instruction)
                    if key not in seen_proposals:
                        seen_proposals.add(key)
                        new_text = f"{current_text}\n{instruction}".strip() if current_text else instruction
                        proposals.append((component, new_text, "failure_driven"))

        # Also support proposing valid json instruction if any json failure exists
        has_json_failure = any(
            f.evaluation_method == "exact_json" or "json" in f.failure_category
            for f in sorted_failures
        )
        if has_json_failure:
            comp, instr = "system", "Always respond with only valid json."
            current = texts.get(comp, "")
            if instr.casefold() not in current.casefold() and (comp, instr) not in seen_proposals:
                seen_proposals.add((comp, instr))
                new_text = f"{current}\n{instr}".strip() if current else instr
                proposals.append((comp, new_text, "failure_driven"))

        return proposals


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of harness optimization across rounds and splits."""

    best: HarnessCandidate
    baseline: HarnessCandidate
    history: list[dict[str, Any]]
    validation: dict[str, float | None]
    holdout_evaluated: bool = False


def persist_candidate(evidence: EvidenceStore, candidate: HarnessCandidate) -> None:
    """Persist candidate as a policy candidate and transition DRAFT -> TRAINED."""
    record = {
        "candidate_id": candidate.candidate_id,
        "kind": "harness",
        "parent_id": candidate.parent_candidate_id,
        "training_id": None,
        "harness": {
            "components": dict(candidate.components),
            "recovery_policy": dict(candidate.recovery_policy),
            "generation_method": candidate.generation_method,
            "training_case_ids": list(candidate.training_case_ids),
        },
    }
    evidence.append("policy_candidates", candidate.candidate_id, record)
    if evidence.state("policy_candidate", candidate.candidate_id) is None:
        evidence.transition(
            "policy_candidate",
            candidate.candidate_id,
            "DRAFT",
            actor="harness_optimizer",
            reason="candidate generated",
        )
    if evidence.state("policy_candidate", candidate.candidate_id) == "DRAFT":
        evidence.transition(
            "policy_candidate",
            candidate.candidate_id,
            "TRAINED",
            actor="harness_optimizer",
            reason="candidate evaluated on training split",
        )


def optimize(
    registry: PromptRegistry,
    evidence: EvidenceStore,
    suite: Suite,
    provider_factory: Callable[[], Provider] | Provider,
    *,
    generator: CandidateGenerator | None = None,
    rounds: int = 4,
    beam: int = 3,
    seed: int = 0,
) -> OptimizationResult:
    """Run beam search optimization over harness candidate components."""
    train_cases = optimizer_cases(suite, ("train",))
    validation_cases = optimizer_cases(suite, ("validation",))
    all_optimizer_cases = list(train_cases) + list(validation_cases)
    train_cases_by_id = {c.case_id: c for c in train_cases}

    rng = random.Random(seed)
    gen = generator if generator is not None else FailureDrivenGenerator()

    # Load and register baseline prompts
    baseline_prompts = registry.load_baseline(DEFAULT_BASELINE_PATH)
    baseline_data = json.loads(DEFAULT_BASELINE_PATH.read_text(encoding="utf-8"))
    baseline_recovery = baseline_data.get("recovery_policy", {})

    baseline_candidate = HarnessCandidate(
        candidate_id="",
        parent_candidate_id=None,
        components={k: v.prompt_id for k, v in sorted(baseline_prompts.items())},
        recovery_policy=baseline_recovery,
        generation_method="baseline",
        training_case_ids=(),
        created_at=utc_now(),
    )

    persist_candidate(evidence, baseline_candidate)

    provider = provider_factory() if callable(provider_factory) else provider_factory
    base_train_eval = evaluate(baseline_candidate, registry, train_cases, provider, split_label="train")
    persist(evidence, base_train_eval)

    candidates: dict[str, HarnessCandidate] = {baseline_candidate.candidate_id: baseline_candidate}
    train_evals: dict[str, HarnessEvaluation] = {baseline_candidate.candidate_id: base_train_eval}
    current_beam: list[HarnessCandidate] = [baseline_candidate]
    history: list[dict[str, Any]] = [
        {
            "candidate_id": baseline_candidate.candidate_id,
            "parent_candidate_id": None,
            "round": 0,
            "train_pass_rate": base_train_eval.pass_rate,
            "generation_method": "baseline",
        }
    ]

    for round_idx in range(1, rounds + 1):
        proposals_to_process: list[tuple[HarnessCandidate, str, str, str]] = []

        for parent in current_beam:
            parent_eval = train_evals[parent.candidate_id]
            failures: list[FailureSummary] = []
            for case_id, res in sorted(parent_eval.per_case.items()):
                if res["passed"] is False:
                    case = train_cases_by_id[case_id]
                    failures.append(
                        FailureSummary(
                            case_id=case.case_id,
                            domain=case.domain,
                            evaluation_method=case.evaluation.method,
                            failure_category=res["failure_category"] or "other",
                        )
                    )

            if not failures:
                continue

            parent_texts = parent.texts(registry)
            proposed = gen.propose(parent, parent_texts, failures, rng)
            for comp, new_text, method in proposed:
                proposals_to_process.append((parent, comp, new_text, method))

        for parent, comp, new_text, method in proposals_to_process:
            # Register new prompt version
            parent_prompt_id = parent.components.get(comp)
            prompt_ver = registry.register(
                comp,
                new_text,
                parent_id=parent_prompt_id,
                generation_method=method,
            )

            child_comps = dict(parent.components)
            child_comps[comp] = prompt_ver.prompt_id

            child = HarnessCandidate(
                candidate_id="",
                parent_candidate_id=parent.candidate_id,
                components=child_comps,
                recovery_policy=dict(parent.recovery_policy),
                generation_method=method,
                training_case_ids=tuple(sorted(train_cases_by_id.keys())),
                created_at=utc_now(),
            )

            # Oracle check across all training and validation cases
            try:
                assert_oracle_free(child.texts(registry), all_optimizer_cases)
            except IntegrityError:
                # Rejected children are never persisted as TRAINED or evaluated
                continue

            if child.candidate_id not in candidates:
                candidates[child.candidate_id] = child
                persist_candidate(evidence, child)
                child_train_eval = evaluate(child, registry, train_cases, provider, split_label="train")
                persist(evidence, child_train_eval)
                train_evals[child.candidate_id] = child_train_eval

                history.append(
                    {
                        "candidate_id": child.candidate_id,
                        "parent_candidate_id": child.parent_candidate_id,
                        "round": round_idx,
                        "train_pass_rate": child_train_eval.pass_rate,
                        "generation_method": method,
                    }
                )

        # Beam selection by train pass rate (descending, ties broken by candidate_id)
        pool = list(candidates.values())
        pool.sort(
            key=lambda c: (
                -(
                    train_evals[c.candidate_id].pass_rate
                    if train_evals[c.candidate_id].pass_rate is not None
                    else -1.0
                ),
                c.candidate_id,
            )
        )
        current_beam = pool[:beam]

    # Evaluate validation split on pool of all candidates
    val_results: dict[str, float | None] = {}
    for cand in candidates.values():
        val_eval = evaluate(cand, registry, validation_cases, provider, split_label="validation")
        persist(evidence, val_eval)
        val_results[cand.candidate_id] = val_eval.pass_rate

    # Select best by validation pass rate (descending), ties -> fewer characters, then candidate_id
    def _val_sort_key(c: HarnessCandidate) -> tuple[float, int, str]:
        vr = val_results.get(c.candidate_id)
        neg_rate = -(vr if vr is not None else -1.0)
        char_count = sum(len(txt) for txt in c.texts(registry).values())
        return (neg_rate, char_count, c.candidate_id)

    best_candidate = min(candidates.values(), key=_val_sort_key)

    return OptimizationResult(
        best=best_candidate,
        baseline=baseline_candidate,
        history=history,
        validation=val_results,
        holdout_evaluated=False,
    )
