"""Tests for candidate-based harness optimization, immutability, isolation, and export."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from model_lab.datasets import load_core_suite, optimizer_cases
from model_lab.errors import IntegrityError, ValidationError
from model_lab.optimization.harness.candidate import (
    HarnessCandidate,
    assert_oracle_free,
    candidate_digest,
)
from model_lab.optimization.harness.exporter import bundle_files, export_bundle
from model_lab.optimization.harness.metric_adapter import (
    HarnessEvaluation,
    classify_failure,
    evaluate,
    persist,
)
from model_lab.optimization.harness.optimizer import (
    FailureDrivenGenerator,
    FailureSummary,
    OptimizationResult,
    optimize,
)
from model_lab.optimization.harness.prompt_registry import (
    COMPONENTS,
    PromptRegistry,
    PromptVersion,
    prompt_digest,
)
from model_lab.optimization.harness.simulated import (
    PromptSensitiveProvider,
    simulated_task,
)
from model_lab.schemas import Attempt, AttemptStatus, Grade, ModelConfig, utc_now
from model_lab.storage.evidence import EvidenceStore
from model_lab.storage.sqlite import SQLiteStore


@pytest.fixture
def evidence_store(tmp_path: Path) -> EvidenceStore:
    store = SQLiteStore(tmp_path / "test_harness.sqlite3")
    return EvidenceStore(store)


@pytest.fixture
def prompt_registry(evidence_store: EvidenceStore) -> PromptRegistry:
    return PromptRegistry(evidence_store)


def test_prompt_version_validation_and_components():
    """Verify prompt component validation, digest calculation, and immutability."""
    assert "system" in COMPONENTS
    assert "recovery" in COMPONENTS

    digest = prompt_digest("system", "Test text", None)
    assert digest.startswith("prm-")

    ver = PromptVersion(
        prompt_id="",
        component="system",
        text="Test text",
        parent_id=None,
        generation_method="manual",
        created_at=utc_now(),
    )
    assert ver.prompt_id == digest

    with pytest.raises(ValidationError):
        PromptVersion(
            prompt_id="",
            component="non_existent_component",
            text="Test text",
            parent_id=None,
            generation_method="manual",
            created_at=utc_now(),
        )


def test_prompt_registry_idempotency_and_immutability(prompt_registry: PromptRegistry, evidence_store: EvidenceStore):
    """Registering identical text twice gives same prompt_id and one row; no mutation."""
    text = "You are a helpful assistant."
    p1 = prompt_registry.register("system", text, generation_method="test_method")
    p2 = prompt_registry.register("system", text, generation_method="test_method")

    assert p1.prompt_id == p2.prompt_id
    assert p1.text == text
    assert p1.component == "system"

    count = evidence_store.count("harness_prompts", component="system")
    assert count == 1

    with pytest.raises((AttributeError, TypeError)):
        p1.text = "modified text"  # type: ignore

    fetched = prompt_registry.get(p1.prompt_id)
    assert fetched.prompt_id == p1.prompt_id
    assert fetched.text == p1.text


def test_prompt_lineage_ordering(prompt_registry: PromptRegistry):
    """Verify lineage returns versions root first."""
    root = prompt_registry.register("system", "Root instruction.", parent_id=None)
    mid = prompt_registry.register("system", "Root instruction.\nRefined.", parent_id=root.prompt_id)
    leaf = prompt_registry.register("system", "Root instruction.\nRefined.\nFinal.", parent_id=mid.prompt_id)

    lineage = prompt_registry.lineage(leaf.prompt_id)
    assert len(lineage) == 3
    assert lineage[0].prompt_id == root.prompt_id
    assert lineage[1].prompt_id == mid.prompt_id
    assert lineage[2].prompt_id == leaf.prompt_id


def test_candidate_content_addressed_and_texts(prompt_registry: PromptRegistry):
    """Verify HarnessCandidate digest is deterministic and texts() looks up all components."""
    p_sys = prompt_registry.register("system", "System instructions.")
    p_rec = prompt_registry.register("recovery", "Recovery instructions.")

    components = {"system": p_sys.prompt_id, "recovery": p_rec.prompt_id}
    policy = {"max_retries": 1, "retry_on": ["timeout"]}

    cand1 = HarnessCandidate(
        candidate_id="",
        parent_candidate_id=None,
        components=components,
        recovery_policy=policy,
        generation_method="test",
        training_case_ids=("case-1",),
    )
    cand2 = HarnessCandidate(
        candidate_id="",
        parent_candidate_id=None,
        components=components,
        recovery_policy=policy,
        generation_method="test",
        training_case_ids=("case-1",),
    )

    expected_id = candidate_digest(components, policy)
    assert cand1.candidate_id == expected_id
    assert cand1.candidate_id == cand2.candidate_id

    texts = cand1.texts(prompt_registry)
    assert texts["system"] == "System instructions."
    assert texts["recovery"] == "Recovery instructions."


def test_oracle_isolation_assertion(prompt_registry: PromptRegistry):
    """Assert assert_oracle_free catches reference answers and rubrics."""
    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))
    case = train_cases[0]

    ref_answer = case.evaluation.reference_answer
    assert isinstance(ref_answer, str)

    clean_texts = {"system": "Standard clean assistant instructions."}
    assert_oracle_free(clean_texts, train_cases)

    contaminated_ref = {"system": f"Answer like this: {ref_answer}"}
    with pytest.raises(IntegrityError, match="Oracle contamination detected"):
        assert_oracle_free(contaminated_ref, train_cases)

    rubric_criterion = case.evaluation.rubric[0].criterion
    contaminated_rubric = {"system": f"Ensure {rubric_criterion} in response"}
    with pytest.raises(IntegrityError, match="Oracle contamination detected"):
        assert_oracle_free(contaminated_rubric, train_cases)


def test_generator_oracle_leak_rejected_in_optimizer(prompt_registry: PromptRegistry, evidence_store: EvidenceStore):
    """A generator that injects reference answers is rejected before evaluation/persistence as TRAINED."""
    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))
    leaked_ref = train_cases[0].evaluation.reference_answer

    class LeakingGenerator:
        def propose(self, parent, texts, failures, rng):
            return [("system", f"Always say {leaked_ref}", "leak_method")]

    outputs, skills = simulated_task(train_cases)
    provider = PromptSensitiveProvider(outputs=outputs, skills=skills)

    res = optimize(
        prompt_registry,
        evidence_store,
        suite,
        lambda: provider,
        generator=LeakingGenerator(),
        rounds=1,
        beam=1,
        seed=42,
    )

    assert res.best.candidate_id == res.baseline.candidate_id

    history = evidence_store.history("policy_candidate", res.best.candidate_id)
    assert any(h["to_state"] == "TRAINED" for h in history)

    states = evidence_store.states("policy_candidate")
    assert len(states) == 1
    assert res.baseline.candidate_id in states


def test_failure_summary_carries_no_reference_text(prompt_registry: PromptRegistry, evidence_store: EvidenceStore):
    """FailureSummary objects handed to generators contain only (case_id, domain, evaluation_method, failure_category)."""
    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))
    captured_summaries: list[FailureSummary] = []

    class InspectingGenerator:
        def propose(self, parent, texts, failures, rng):
            captured_summaries.extend(failures)
            return []

    outputs, skills = simulated_task(train_cases)
    provider = PromptSensitiveProvider(outputs=outputs, skills=skills)

    optimize(
        prompt_registry,
        evidence_store,
        suite,
        lambda: provider,
        generator=InspectingGenerator(),
        rounds=1,
        beam=1,
        seed=1,
    )

    assert len(captured_summaries) > 0
    allowed_fields = {"case_id", "domain", "evaluation_method", "failure_category"}
    for summary in captured_summaries:
        assert isinstance(summary, FailureSummary)
        assert set(summary.__dataclass_fields__.keys()) == allowed_fields
        for field_name in allowed_fields:
            val = getattr(summary, field_name)
            assert isinstance(val, str)
            assert "thank you" not in val.lower()
            assert "agenda" not in val.lower()


def test_optimizer_source_has_no_holdout_references():
    """Optimizer source must not import or reference holdout_cases, and optimizer_cases('holdout') must raise."""
    optimizer_path = Path(__file__).resolve().parent.parent / "model_lab" / "optimization" / "harness" / "optimizer.py"
    source = optimizer_path.read_text(encoding="utf-8")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "holdout_cases":
            pytest.fail("optimizer.py contains reference to holdout_cases name")
        if isinstance(node, ast.Attribute) and node.attr == "holdout_cases":
            pytest.fail("optimizer.py contains attribute access to holdout_cases")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "holdout_cases" in node.value:
            pytest.fail("optimizer.py contains string mentioning holdout_cases")

    suite = load_core_suite()
    with pytest.raises(IntegrityError):
        optimizer_cases(suite, ("holdout",))


def test_metric_adapter_classify_and_persist(evidence_store: EvidenceStore, prompt_registry: PromptRegistry):
    """Test failure classification, metric adapter evaluate, and persistence into evidence."""
    cfg = ModelConfig(provider="fake", model="m1")
    att = Attempt(
        attempt_id="att-test1",
        run_id="run-test1",
        logical_request_id="req-test1",
        case_id="case-test1",
        model_config=cfg,
        prompt_hash="a" * 64,
        response_text='{"bad": ',
        status=AttemptStatus.SUCCESS,
        started_at=utc_now(),
    )
    grade = Grade(
        grade_id="grd-test1",
        attempt_id=att.attempt_id,
        grader_id="exact_json",
        grader_version="1.0",
        method="exact_json",
        passed=False,
        score=0.0,
        failure_reason="candidate output is not valid JSON",
        evidence={},
        created_at=utc_now(),
    )

    cat = classify_failure(grade, att)
    assert cat == "invalid_json"

    p = prompt_registry.register("system", "Test assistant text.")
    cand = HarnessCandidate("", None, {"system": p.prompt_id}, {}, "test", ())
    eval_record = HarnessEvaluation(
        candidate_id=cand.candidate_id,
        split="train",
        case_ids=("case-test1",),
        per_case={"case-test1": {"passed": False, "score": 0.0, "failure_category": cat}},
        pass_rate=0.0,
        decided=1,
        abstained=0,
        evidence_class="SIMULATED",
    )
    persist(evidence_store, eval_record)
    assert evidence_store.exists("harness_evaluations", f"{cand.candidate_id}:train")

    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))[:2]
    outputs, skills = simulated_task(train_cases)
    provider = PromptSensitiveProvider(outputs=outputs, skills=skills)
    ev = evaluate(cand, prompt_registry, train_cases, provider, split_label="train")
    assert isinstance(ev, HarnessEvaluation)
    assert ev.split == "train"


def test_simulated_optimization_improves_validation_and_is_deterministic(
    prompt_registry: PromptRegistry,
    evidence_store: EvidenceStore,
    tmp_path: Path,
):
    """In simulated environment, best candidate has validation pass rate > baseline and is deterministic."""
    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))
    val_cases = optimizer_cases(suite, ("validation",))
    all_cases = list(train_cases) + list(val_cases)

    outputs, skills = simulated_task(all_cases)
    provider = PromptSensitiveProvider(outputs=outputs, skills=skills)

    gen = FailureDrivenGenerator()

    # Run 1
    res1 = optimize(
        prompt_registry,
        evidence_store,
        suite,
        lambda: provider,
        generator=gen,
        rounds=3,
        beam=3,
        seed=123,
    )

    assert isinstance(res1, OptimizationResult)
    baseline_val_pass_rate = res1.validation[res1.baseline.candidate_id]
    best_val_pass_rate = res1.validation[res1.best.candidate_id]

    assert baseline_val_pass_rate == 0.0 or baseline_val_pass_rate is None
    assert best_val_pass_rate is not None
    assert best_val_pass_rate > (baseline_val_pass_rate or 0.0)
    assert res1.holdout_evaluated is False

    baseline_prompts = prompt_registry.load_baseline()
    for _comp, prompt in baseline_prompts.items():
        reloaded = prompt_registry.get(prompt.prompt_id)
        assert reloaded.text == prompt.text

    # Run 2 on fresh store with identical seed must yield identical result
    store2 = SQLiteStore(tmp_path / "test_harness_2.sqlite3")
    evidence2 = EvidenceStore(store2)
    registry2 = PromptRegistry(evidence2)

    res2 = optimize(
        registry2,
        evidence2,
        suite,
        lambda: provider,
        generator=gen,
        rounds=3,
        beam=3,
        seed=123,
    )

    assert res1.best.candidate_id == res2.best.candidate_id
    assert res1.validation == res2.validation
    assert [h["candidate_id"] for h in res1.history] == [h["candidate_id"] for h in res2.history]


def test_exported_bundle_round_trips_and_contains_no_oracles(
    prompt_registry: PromptRegistry,
    evidence_store: EvidenceStore,
    tmp_path: Path,
):
    """Exported prompts.json round-trips and contains no reference answers."""
    suite = load_core_suite()
    train_cases = optimizer_cases(suite, ("train",))
    val_cases = optimizer_cases(suite, ("validation",))
    all_cases = list(train_cases) + list(val_cases)

    outputs, skills = simulated_task(all_cases)
    provider = PromptSensitiveProvider(outputs=outputs, skills=skills)

    res = optimize(
        prompt_registry,
        evidence_store,
        suite,
        lambda: provider,
        rounds=2,
        beam=2,
        seed=42,
    )

    out_dir = tmp_path / "exported_bundle"
    files = export_bundle(res.best, prompt_registry, out_dir)

    assert files["prompts.json"].exists()
    assert files["recovery_policy.json"].exists()

    prompts_data = json.loads(files["prompts.json"].read_text(encoding="utf-8"))
    policy_data = json.loads(files["recovery_policy.json"].read_text(encoding="utf-8"))

    assert prompts_data["candidate_id"] == res.best.candidate_id
    assert prompts_data["harness_schema_version"] == "harness-prompt.v1"
    assert "system" in prompts_data["components"]
    assert "system" in prompts_data["lineage"]

    exported_text = files["prompts.json"].read_text(encoding="utf-8")
    for case in all_cases:
        ref = case.evaluation.reference_answer
        if isinstance(ref, str) and len(ref) >= 8:
            assert ref.lower() not in exported_text.lower()

    bundle_dict = bundle_files(res.best, prompt_registry)
    assert bundle_dict["prompts.json"] == prompts_data
    assert bundle_dict["recovery_policy.json"] == policy_data
