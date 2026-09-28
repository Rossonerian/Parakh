"""Candidate promotion verifier: the only path from TRAINED to VERIFIED.

Hard gates fail the candidate regardless of soft metrics; each gate returns a
machine-readable ``{gate, passed, reason, details}``. Soft metrics (cost,
latency, rubric, frontier migration, recovery) are reported for ranking only.
This is the one module allowed to read the sealed holdout (dataset holdout via
``sealed_holdout("verification")`` and the core holdout role).

Verification never exports and never approves: a passing report moves the
candidate to VERIFIED; APPROVED requires a named operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from model_lab.artifacts.provenance import git_state
from model_lab.datasets import holdout_cases, load_core_suite, optimizer_cases
from model_lab.domain.isolation import assert_candidate_safe
from model_lab.errors import IntegrityError
from model_lab.optimization.benchmark_evidence import evidence_table
from model_lab.optimization.regression import deterministic_regressions, evaluate_policy, non_inferior
from model_lab.optimization.router import off_policy, replay
from model_lab.optimization.router.dataset import load_dataset
from model_lab.optimization.router.features import extract, feature_schema
from model_lab.optimization.router.linucb import from_policy_document
from model_lab.optimization.router.policies import LinUCBPolicy, cheapest, flagship
from model_lab.optimization.router.trainer import reproduce
from model_lab.optimization.harness import HarnessCandidate, PromptRegistry, assert_oracle_free
from model_lab.optimization.harness import evaluate as evaluate_harness
from model_lab.optimization.harness import persist as persist_harness_evaluation
from model_lab.providers.base import Provider
from model_lab.schema_registry import VERIFICATION_SCHEMA_VERSION
from model_lab.schemas import Case, stable_hash, utc_now
from model_lab.storage.evidence import EvidenceStore

HarnessProviderFactory = Callable[[Sequence[Case]], Provider]

SYNTHETIC_PRODUCERS = frozenset({"parakh-synthetic-karmi"})


@dataclass(frozen=True)
class VerifierConfig:
    ope_margin: float = 0.02               # overall: lower 95% bound of (candidate - logging) >= -margin
    segment_margin: float = 0.05           # per domain / tier, same paired-bootstrap rule
    min_segment_examples: int = 30         # smaller segments are reported as unverified
    critical_domains: tuple[str, ...] = ("privacy", "automation", "expenses")
    critical_failure_margin: float = 0.01
    tool_failure_margin: float = 0.02
    holdout_margin: float = 0.03
    core_allowed_drop: float = 0.0         # deterministic core regression: zero tolerance
    rubric_margin: float = 0.05            # stochastic (human/judge) scores: paired bootstrap margin
    min_ess: float = 30.0
    min_support: float = 0.95
    bootstrap_resamples: int = 400
    # Absolute per-tier ceilings are owner inputs (Tier_Entitlements.md: unapproved until measured).
    # Unconfigured tiers are bounded relative to the logging (current production) policy instead.
    tier_cost_ceiling_usd: Mapping[str, float] = field(default_factory=dict)
    tier_latency_ceiling_ms: Mapping[str, float] = field(default_factory=dict)
    cost_increase_margin: float = 0.25     # relative bound: candidate <= logging * (1 + margin)
    latency_increase_margin: float = 0.25
    harness_holdout_margin: float = 0.0    # harness candidate holdout pass rate >= baseline - margin
    seed: int = 0


def _gate(gate: str, passed: bool, reason: str, **details: Any) -> dict[str, Any]:
    return {"gate": gate, "passed": bool(passed), "reason": reason, "details": details}


def _logging_values(examples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return off_policy.on_policy_value(list(examples))


def _field_mean(examples: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [e[key] for e in examples if e.get(key) is not None]
    return sum(float(v) for v in values) / len(values) if values else None


def registry_for_imports(evidence: EvidenceStore, import_ids: Sequence[str]) -> list[dict[str, Any]]:
    """Model registry entries declared by the given telemetry imports (first declaration wins), sorted by action."""
    out: dict[str, dict[str, Any]] = {}
    for import_id in import_ids:
        for entry in evidence.get("telemetry_imports", import_id).get("model_registry", []):
            out.setdefault(f"{entry['provider']}/{entry['model']}", dict(entry))
    return [out[k] for k in sorted(out)]


def registry_for(evidence: EvidenceStore, dataset: Any) -> list[dict[str, Any]]:
    """Model registry of the imports a dataset was built from."""
    return registry_for_imports(evidence, (dataset.metadata.get("source") or {}).get("import_ids", []))


def verify(evidence: EvidenceStore, candidate_id: str, *, benchmark_runs: Mapping[str, str], config: VerifierConfig | None = None,
           git: Mapping[str, Any] | None = None, harness_candidate_id: str | None = None,
           harness_provider: HarnessProviderFactory | None = None, actor: str = "verifier") -> dict[str, Any]:
    """Run every gate, persist the report, and move TRAINED -> VERIFIED only if all hard gates pass.

    With ``harness_candidate_id`` the harness candidate is verified in the same report (oracle
    isolation over its real prompt texts, validation and sealed-holdout non-degradation against its
    baseline) and moves to VERIFIED with the router. ``harness_provider`` builds the provider for
    the holdout cases; without it the harness holdout gate fails closed.
    """
    config = config or VerifierConfig()
    state = evidence.state("policy_candidate", candidate_id)
    if state not in ("TRAINED", "VERIFIED"):
        raise IntegrityError(f"{candidate_id} is {state}; only TRAINED candidates are verified")
    candidate = evidence.get("policy_candidates", candidate_id)
    model = from_policy_document(candidate["policy"])
    dataset = load_dataset(evidence, candidate["dataset_id"])
    validation = list(dataset.examples_for("validation"))
    holdout = list(dataset.sealed_holdout("verification"))
    registry = registry_for(evidence, dataset)
    policy = LinUCBPolicy(model)
    cheap, premium = cheapest(registry), flagship(registry)
    ope_kwargs = {"seed": config.seed, "min_ess": config.min_ess, "min_support": config.min_support}
    gates: list[dict[str, Any]] = []

    # --- integrity gates -------------------------------------------------------------
    suite = load_core_suite()
    leaks = []
    for case in suite.cases:
        try:
            assert_candidate_safe(case.candidate_payload())
        except Exception as exc:  # any failure is a leak finding
            leaks.append(f"{case.case_id}: {exc}")
    exported_text = str(candidate["policy"]) + str(candidate["feature_schema"])
    leaks += [c.case_id for c in suite.cases if isinstance(c.evaluation.reference_answer, str) and len(c.evaluation.reference_answer) >= 8
              and c.evaluation.reference_answer in exported_text]
    harness_evidence: dict[str, Any] | None = None
    if harness_candidate_id:
        harness_gates, harness_evidence = _harness_gates(evidence, harness_candidate_id, suite, config, harness_provider)
        gates.extend(harness_gates)
    gates.append(_gate("oracle_isolation", not leaks, "no oracle material reachable" if not leaks else "oracle leakage", findings=leaks[:10]))
    current = feature_schema()
    gates.append(_gate("feature_schema_compatible", candidate["feature_schema"].get("schema_id") == current["schema_id"]
                       and dataset.metadata.get("feature_schema_version") == current["feature_schema_version"],
                       "candidate, dataset and current feature schema agree", candidate=candidate["feature_schema"].get("schema_id"), current=current["schema_id"]))
    repro = reproduce(evidence, candidate["training_id"])
    gates.append(_gate("reproducible", repro["reproducible"] and repro["parameters_checksum_match"], "retraining reproduces parameters", **repro))
    git = dict(git or git_state())
    gates.append(_gate("provenance_ready", bool(git.get("commit")) and git.get("dirty") is False,
                       "git commit known and tree clean" if git.get("dirty") is False else "dirty or unknown git tree: artifact not reproducible", git=git))

    # --- off-policy gates on validation ------------------------------------------------
    report = off_policy.evaluate(policy, validation, **ope_kwargs)
    logging = _logging_values(validation)
    gates.append(_gate("ope_support", report["reliable"], "logged data supports the candidate" if report["reliable"] else "insufficient support: no strong counterfactual conclusion",
                       warnings=report["warnings"], ess=report["ess"], support=report["support"]))
    overall = off_policy.paired_difference(policy, validation, margin=config.ope_margin, seed=config.seed, resamples=config.bootstrap_resamples)
    gates.append(_gate("ope_non_inferior", overall["verdict"] == "non_inferior",
                       f"validation: lower 95% bound of candidate - logging >= -{config.ope_margin} ({overall['verdict']})",
                       candidate=report["snips"], logging=logging["value"], difference=overall["difference"], ci=overall["ci"]))
    segment_failures, unverified, segments = [], [], {}
    for segment in ("task_domain", "tier"):
        groups: dict[str, list[dict[str, Any]]] = {}
        for example in validation:
            if example.get(segment) is not None:
                groups.setdefault(example[segment], []).append(example)
        for value, examples in sorted(groups.items()):
            label = f"{segment}={value}"
            critical = segment == "tier" or value in config.critical_domains
            if len(examples) < config.min_segment_examples:
                unverified.append(f"{label} (n={len(examples)})")
                if critical:
                    segment_failures.append(f"{label}: only {len(examples)} examples (critical segment needs {config.min_segment_examples})")
                continue
            result = off_policy.paired_difference(policy, examples, margin=config.segment_margin, seed=config.seed,
                                                  resamples=config.bootstrap_resamples)
            segments[label] = result
            below = result["difference"] is None or result["difference"] < -config.segment_margin
            if result["verdict"] == "worse" or (critical and below):
                segment_failures.append(f"{label}: {result['verdict']} (difference {result['difference']}, ci {result['ci']})")
            elif result["verdict"] == "inconclusive":
                unverified.append(f"{label} (inconclusive, n={len(examples)}, ci {result['ci']})")
    gates.append(_gate("segment_non_inferior", not segment_failures,
                       "no segment confidently worse; no tier or critical domain estimated below margin",
                       failures=segment_failures, unverified=unverified, segments=segments))
    crit_logging = _field_mean(validation, "critical")
    crit = report.get("critical_failure_rate")
    gates.append(_gate("critical_failures", crit is not None and crit_logging is not None and crit <= crit_logging + config.critical_failure_margin,
                       "critical failure rate not above logging", candidate=crit, logging=crit_logging))
    tool = off_policy.evaluate(policy, validation, reward_key="tool_failure_penalty", bootstrap=0, direct_method=False, **ope_kwargs)
    tool_logging = _field_mean(validation, "tool_failure_penalty")
    gates.append(_gate("tool_schema_failures", tool["snips"] is not None and tool_logging is not None and tool["snips"] <= tool_logging + config.tool_failure_margin,
                       "tool/schema failure penalty not increased", candidate=tool["snips"], logging=tool_logging))
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for example in validation:
        by_tier.setdefault(example["tier"], []).append(example)
    for gate, field_name, key, ceilings, increase in (
            ("tier_budget", "cost", "expected_cost", config.tier_cost_ceiling_usd, config.cost_increase_margin),
            ("tier_latency", "latency_ms", "expected_latency", config.tier_latency_ceiling_ms, config.latency_increase_margin)):
        failures, bounds = {}, {}
        for tier, examples in sorted(by_tier.items()):
            value = off_policy.evaluate(policy, examples, bootstrap=0, direct_method=False,
                                        **{k: v for k, v in ope_kwargs.items() if k != "seed"})[key]
            baseline = _field_mean(examples, field_name) if all(e.get(field_name) is not None for e in examples) else None
            if tier in ceilings:
                bound, source = float(ceilings[tier]), "owner_ceiling"
            else:
                bound, source = (baseline * (1 + increase) if baseline is not None else None), f"logging_x{1 + increase:g}"
            bounds[tier] = {"candidate": value, "logging": baseline, "bound": bound, "source": source}
            if value is None or bound is None or value > bound:
                failures[tier] = bounds[tier]
        unit = "cost" if gate == "tier_budget" else "latency"
        gates.append(_gate(gate, not failures, f"expected {unit} within every tier bound (owner ceiling, else logging + margin; unknown fails)",
                           failures=failures, tiers=bounds))

    # --- frozen core regression (train+validation roles) and holdout --------------------
    table = evidence_table(evidence.store, benchmark_runs)
    tier_actions = {t: sorted(set(a)) for t, a in _observed_tier_actions(dataset).items()}

    def choose_candidate(context: Mapping[str, Any], eligible: Sequence[str]) -> str | None:
        return model.greedy(extract(context), eligible) if set(eligible) & set(model.actions) else None

    baseline_choice = _empirical_static_policy(dataset)
    open_cases = optimizer_cases(suite, ("train", "validation"))
    core_candidate = evaluate_policy(choose_candidate, open_cases, table, tier_actions=tier_actions, registry=registry)
    core_baseline = evaluate_policy(baseline_choice, open_cases, table, tier_actions=tier_actions, registry=registry)
    regressions = deterministic_regressions(core_candidate, core_baseline, allowed_drop=config.core_allowed_drop)
    stochastic = _rubric_check(core_candidate, core_baseline, config)
    gates.append(_gate("core_regression", not regressions and not core_candidate["unsupported"] and stochastic.get("non_inferior") is not False,
                       "no deterministic regression, full evidence support, rubric non-inferior", regressions=regressions,
                       unsupported=core_candidate["unsupported"][:20], rubric=stochastic,
                       candidate=core_candidate["overall"], baseline=core_baseline["overall"]))
    holdout_report = off_policy.evaluate(policy, holdout, **ope_kwargs)
    holdout_logging = _logging_values(holdout)
    core_holdout_c = evaluate_policy(choose_candidate, holdout_cases(suite), table, tier_actions=tier_actions, registry=registry)
    core_holdout_b = evaluate_policy(baseline_choice, holdout_cases(suite), table, tier_actions=tier_actions, registry=registry)
    holdout_regressions = deterministic_regressions(core_holdout_c, core_holdout_b, allowed_drop=config.core_allowed_drop, group="by_role")
    holdout_rubric = _rubric_check(core_holdout_c, core_holdout_b, config)
    core_holdout_evidence = {"decided": core_holdout_c["overall"]["decided"], "rubric_pairs": holdout_rubric.get("n", 0)}
    telemetry_holdout = off_policy.paired_difference(policy, holdout, margin=config.holdout_margin, seed=config.seed,
                                                     resamples=config.bootstrap_resamples)
    telemetry_ok = (telemetry_holdout["verdict"] != "worse" and telemetry_holdout["difference"] is not None
                    and telemetry_holdout["difference"] >= -config.holdout_margin)
    holdout_ok = (telemetry_ok and not holdout_regressions and not core_holdout_c["unsupported"]
                  and holdout_rubric.get("non_inferior") is not False)
    gates.append(_gate("holdout", holdout_ok, "sealed telemetry holdout and core holdout not degraded",
                       telemetry=telemetry_holdout, telemetry_candidate=holdout_report["snips"], telemetry_logging=holdout_logging["value"],
                       warnings=holdout_report["warnings"], core_regressions=holdout_regressions, core_rubric=holdout_rubric,
                       core_evidence=core_holdout_evidence))
    holdout_notes = []
    if not core_holdout_evidence["decided"] and not core_holdout_evidence["rubric_pairs"]:
        holdout_notes.append("Core-benchmark holdout cases are rubric-only and have no blind-review scores for the chosen actions: "
                     "the core holdout is unverified; the holdout gate rests on the sealed telemetry holdout.")

    # --- soft metrics -------------------------------------------------------------------
    baselines = replay.compare([policy, cheap, premium], validation, segments=(), bootstrap=0, direct_method=False, **ope_kwargs)["overall"]
    cost_by_action = {f"{m['provider']}/{m['model']}": m["estimated_input_cost_per_token"] + m["estimated_output_cost_per_token"] for m in registry}
    soft = {
        "expected_reward": {name: r["snips"] for name, r in baselines.items()} | {"logging": logging["value"]},
        "expected_cost": report.get("expected_cost"), "expected_latency_ms": report.get("expected_latency"),
        "success_rate": report.get("success_rate"), "action_distribution": report.get("action_distribution"),
        "frontier_migration": replay.frontier_migration(policy, cheap, validation, cost_by_action),
        "reward_per_dollar": (report["snips"] / report["expected_cost"]) if report.get("expected_cost") and report.get("snips") is not None else None,
        "train_validation_gap": _overfit_gap(evidence, candidate, report),
        "holdout_gap": (report["snips"] - holdout_report["snips"]) if None not in (report["snips"], holdout_report["snips"]) else None,
        "core_rubric_mean": core_candidate["overall"]["rubric_mean"],
    }
    evidence_classes = {row["evidence_class"] for row in core_candidate["rows"] if row["evidence_class"]}
    producers = {evidence.get("telemetry_imports", i)["producer_repo"] for i in (dataset.metadata.get("source") or {}).get("import_ids", [])}
    evidence_classes.add("SIMULATED" if producers & SYNTHETIC_PRODUCERS else "MEASURED")
    evidence_class = evidence_classes.pop() if len(evidence_classes) == 1 else "MIXED"
    passed = all(g["passed"] for g in gates)
    graders = sorted({row["grader"] for row in table.values() if row.get("grader")})
    body = {
        "policy_candidate_id": candidate_id, "schema_version": VERIFICATION_SCHEMA_VERSION, "passed": passed,
        "evidence_class": evidence_class, "dataset_id": dataset.dataset_id, "harness_candidate_id": harness_candidate_id,
        "harness": harness_evidence,
        "hard_gates": gates, "failed_gates": [g["gate"] for g in gates if not g["passed"]], "soft_metrics": soft,
        "ope": {"validation": report, "holdout": holdout_report, "logging_validation": logging},
        "core_regression": {"candidate": {k: v for k, v in core_candidate.items() if k != "rows"},
                            "baseline": {k: v for k, v in core_baseline.items() if k != "rows"}},
        "evaluation_run_ids": sorted(benchmark_runs.values()), "human_review_run_ids": sorted({row["run_id"] for row in table.values() if row["rubric_scores"]}),
        "grader_versions": {g.split("@")[0]: g.split("@")[1] for g in graders}, "config": _config_dict(config),
        "limitations": _limitations(evidence_class, report, unverified, config, sorted({e["tier"] for e in validation})) + holdout_notes,
    }
    report_id = "ver-" + stable_hash(body)[:20]
    if evidence.exists("verification_reports", report_id):
        record = evidence.get("verification_reports", report_id)
    else:
        record = {"report_id": report_id, "created_at": utc_now(), **body}
        evidence.append("verification_reports", report_id, record)
    if passed and state == "TRAINED":
        evidence.transition("policy_candidate", candidate_id, "VERIFIED", actor=actor, reason=f"all hard gates passed ({report_id})")
        if harness_candidate_id and evidence.state("policy_candidate", harness_candidate_id) == "TRAINED":
            evidence.transition("policy_candidate", harness_candidate_id, "VERIFIED", actor=actor,
                                reason=f"verified with router {candidate_id} ({report_id})")
    return record


def approve(evidence: EvidenceStore, candidate_id: str, *, actor: str, reason: str) -> dict[str, Any]:
    """Operator approval of a VERIFIED candidate (a human decision, never automatic)."""
    return evidence.transition("policy_candidate", candidate_id, "APPROVED", actor=actor, reason=reason)


def _harness_root(evidence: EvidenceStore, record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Follow parent links to the baseline harness the candidate was optimized from."""
    seen = set()
    while record.get("parent_id"):
        if record["candidate_id"] in seen:
            raise IntegrityError("harness candidate lineage contains a cycle")
        seen.add(record["candidate_id"])
        record = evidence.get("policy_candidates", record["parent_id"])
    return record


def _harness_gates(evidence: EvidenceStore, harness_candidate_id: str, suite: Any, config: VerifierConfig,
                   harness_provider: HarnessProviderFactory | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Oracle isolation over the real prompt texts, then validation + sealed-holdout non-degradation vs baseline."""
    record = evidence.get("policy_candidates", harness_candidate_id)
    state = evidence.state("policy_candidate", harness_candidate_id)
    candidate = HarnessCandidate.from_record(record)
    baseline = HarnessCandidate.from_record(_harness_root(evidence, record))
    registry = PromptRegistry(evidence)
    gates = []
    try:
        assert_oracle_free(candidate.texts(registry), suite.cases)
        leak = None
    except IntegrityError as exc:
        leak = str(exc)
    gates.append(_gate("harness_oracle_isolation", leak is None and state in ("TRAINED", "VERIFIED"),
                       "harness prompt texts contain no reference/rubric material" if leak is None else "harness oracle leakage",
                       finding=leak, state=state))

    def stored(candidate_id: str, split: str) -> float | None:
        key = f"{candidate_id}:{split}"
        return evidence.get("harness_evaluations", key)["pass_rate"] if evidence.exists("harness_evaluations", key) else None

    validation = {"candidate": stored(candidate.candidate_id, "validation"), "baseline": stored(baseline.candidate_id, "validation")}
    details: dict[str, Any] = {"baseline_candidate_id": baseline.candidate_id, "validation": validation, "holdout": None,
                               "evidence_class": None}
    if harness_provider is None:
        gates.append(_gate("harness_holdout", False, "no harness provider configured: sealed holdout not evaluated", **details))
        return gates, details
    cases = holdout_cases(suite)
    provider = harness_provider(cases)
    results = {}
    for label, item in (("candidate", candidate), ("baseline", baseline)):
        evaluation = evaluate_harness(item, registry, cases, provider, split_label="holdout")
        persist_harness_evaluation(evidence, evaluation)
        results[label] = evaluation.pass_rate
        details["evidence_class"] = evaluation.evidence_class
    details["holdout"] = results
    vc, vb = validation.get("candidate"), validation.get("baseline")
    rc, rb = results.get("candidate"), results.get("baseline")
    ok = (
        vc is not None and vb is not None and vc >= vb
        and rc is not None and rb is not None and rc >= rb - config.harness_holdout_margin
    )
    if None in results.values():
        reason = ("no deterministically graded holdout case: the sealed holdout is rubric-only, so harness holdout "
                  "evidence needs blind human review of the candidate's outputs")
    else:
        reason = "harness validation and sealed holdout not below baseline"
    gates.append(_gate("harness_holdout", ok, reason, **details))
    return gates, details


def _observed_tier_actions(dataset: Any) -> dict[str, set[str]]:
    tiers: dict[str, set[str]] = {}
    for example in dataset.examples_for("train"):
        tiers.setdefault(example["tier"], set()).update(example["eligible_actions"])
    return tiers


def _empirical_static_policy(dataset: Any):
    """Baseline for core regression: the most-logged action per (tier, domain), else per tier."""
    counts: dict[tuple[str, str], dict[str, int]] = {}
    tier_counts: dict[str, dict[str, int]] = {}
    for e in dataset.examples_for("train"):
        counts.setdefault((e["tier"], e["task_domain"]), {}).setdefault(e["action"], 0)
        counts[(e["tier"], e["task_domain"])][e["action"]] += 1
        tier_counts.setdefault(e["tier"], {}).setdefault(e["action"], 0)
        tier_counts[e["tier"]][e["action"]] += 1

    def choose(context: Mapping[str, Any], eligible: Sequence[str]) -> str | None:
        for table in (counts.get((context["tier"], context["task_domain"])), tier_counts.get(context["tier"])):
            if table is not None:
                t = table
                ranked = sorted((a for a in t if a in eligible), key=lambda a: (-t[a], a))
                if ranked:
                    return ranked[0]
        return sorted(eligible)[0] if eligible else None
    return choose


def _rubric_check(candidate: Mapping[str, Any], baseline: Mapping[str, Any], config: VerifierConfig) -> dict[str, Any]:
    paired_c, paired_b = [], []
    base_rows = {(r["case_id"], r["tier"]): r for r in baseline["rows"]}
    for row in candidate["rows"]:
        other = base_rows.get((row["case_id"], row["tier"]))
        if other and row["rubric"] is not None and other["rubric"] is not None:
            paired_c.append(row["rubric"])
            paired_b.append(other["rubric"])
    return non_inferior(paired_c, paired_b, margin=config.rubric_margin, seed=config.seed)


def _overfit_gap(evidence: EvidenceStore, candidate: Mapping[str, Any], validation_report: Mapping[str, Any]) -> float | None:
    training = evidence.get("policy_training_runs", candidate["training_id"])
    train_mean = training.get("metrics", {}).get("train_mean_reward")
    return (train_mean - validation_report["snips"]) if None not in (train_mean, validation_report.get("snips")) else None


def _config_dict(config: VerifierConfig) -> dict[str, Any]:
    return {k: (dict(v) if isinstance(v, Mapping) else list(v) if isinstance(v, tuple) else v) for k, v in config.__dict__.items()}


def _limitations(evidence_class: str, report: Mapping[str, Any], unverified: list[str], config: VerifierConfig,
                 tiers: list[str]) -> list[str]:
    notes = []
    if evidence_class != "MEASURED":
        notes.append(f"Evidence class {evidence_class}: synthetic/simulated evidence is not production performance.")
    if report.get("warnings"):
        notes.append("Off-policy estimate warnings: " + ", ".join(report["warnings"]))
    if unverified:
        notes.append(f"{len(unverified)} segments are not individually verified (too few examples or an interval spanning the margin): "
                     + "; ".join(unverified))
    for name, ceilings in (("cost", config.tier_cost_ceiling_usd), ("latency", config.tier_latency_ceiling_ms)):
        missing = [t for t in tiers if t not in ceilings]
        if missing:
            notes.append(f"No owner-approved {name} ceiling for tiers {', '.join(missing)}; bounded relative to the logging policy only.")
    notes.append("Off-policy estimates assume logged propensities are exact and contexts are i.i.d.; they are estimates, not ground truth.")
    return notes
