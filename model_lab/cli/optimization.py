"""Offline optimization operator commands: telemetry -> rewards -> router -> verifier -> PolicyBundleV1.

Every command works on one SQLite evidence file (``--db``) and never dispatches a paid or live
provider call. Simulated evidence is labelled SIMULATED; measured model evidence comes only from the
existing ``pilot run --allow-paid`` path. Promotion is always an explicit operator action (named
``--actor`` and ``--reason``). Nothing here can change Karmi's active policy: bundles only recommend
shadow mode, and ``artifact karmi-check`` loads a bundle into the reference loader's candidate slot.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
from collections import Counter
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from contracts.karmi_reference import loader as karmi
from model_lab.application.optimization_report import write as write_optimization_report
from model_lab.artifacts import bundle, signer
from model_lab.artifacts.provenance import git_state
from model_lab.cli.output import print_json
from model_lab.datasets import load_core_suite, optimizer_cases
from model_lab.errors import IntegrityError, NotFoundError, ValidationError
from model_lab.optimization.benchmark_evidence import run_simulated_evidence
from model_lab.optimization.harness import PromptRegistry, PromptSensitiveProvider, optimize, simulated_task
from model_lab.optimization.metrics import compounding_metrics
from model_lab.optimization.router import off_policy, replay
from model_lab.optimization.router.dataset import build_dataset, load_dataset, persist_dataset
from model_lab.optimization.router.linucb import from_policy_document
from model_lab.optimization.router.policies import LinUCBPolicy, cheapest, flagship
from model_lab.optimization.router.trainer import train_candidate
from model_lab.preferences.exporter import export_approved, readiness
from model_lab.preferences.extractor import extract_pairs, review
from model_lab.rewards.composite import persist as persist_reward, reward_for_attempt, reward_for_run
from model_lab.rewards.schema import RewardConfig
from model_lab.schema_registry import FEATURE_SCHEMA_VERSION, MINIMUM_KARMI_VERSION, REWARD_SCHEMA_VERSION
from model_lab.schemas import stable_hash
from model_lab.storage import SQLiteStore
from model_lab.storage.evidence import CANDIDATE_ROLES, EvidenceStore
from model_lab.telemetry import synthetic
from model_lab.telemetry.curation import approve as approve_candidate, list_candidates, reject as reject_candidate
from model_lab.telemetry.importer import import_batch
from model_lab.telemetry.schema import RunRecord, parse_run
from model_lab import verifier

COMMANDS = frozenset({"telemetry", "candidates", "preferences", "reward", "harness", "verify", "policy", "artifact", "metrics"})
ROUTER_COMMANDS = frozenset({"dataset", "train", "evaluate", "benchmark"})
BASE_POLICIES = {"static": synthetic.static_policy, "balanced_only": synthetic.balanced_only_policy}


def handles(args: argparse.Namespace) -> bool:
    return args.command in COMMANDS or (args.command == "router" and args.router_command in ROUTER_COMMANDS)


def add_parsers(sub: argparse._SubParsersAction, router_sub: argparse._SubParsersAction) -> None:
    def db(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--db", required=True, help="SQLite evidence database")
        return p

    def operator(p: argparse.ArgumentParser) -> None:
        p.add_argument("--actor", required=True, help="named operator (recorded in the audit trail)")
        p.add_argument("--reason", required=True, help="reason recorded with the transition")

    def out(p: argparse.ArgumentParser, help_text: str = "also write the JSON result to this path") -> None:
        p.add_argument("--out", help=help_text)

    telemetry = sub.add_parser("telemetry", help="import, inspect, or synthesize Karmi TelemetryBatchV1 evidence")
    tsub = telemetry.add_subparsers(dest="telemetry_command", required=True)
    t_import = db(tsub.add_parser("import", help="validate, privacy-check and import a batch (idempotent; bad runs quarantined)"))
    t_import.add_argument("batch", help="TelemetryBatchV1 JSON file")
    t_import.add_argument("--source-label", default="karmi")
    t_status = db(tsub.add_parser("status", help="imports with accepted/quarantined counts and quarantine reasons"))
    t_status.add_argument("--import-id")
    t_synth = tsub.add_parser("synthesize", help="write a deterministic SIMULATED TelemetryBatchV1 (synthetic Karmi)")
    t_synth.add_argument("--out", required=True)
    t_synth.add_argument("--seed", type=int, default=7)
    t_synth.add_argument("--batch-index", type=int, default=0)
    t_synth.add_argument("--runs", type=int, default=4000)
    t_synth.add_argument("--epsilon", type=float, default=0.5, help="logging exploration rate (exact propensities are logged)")
    t_synth.add_argument("--base-policy", choices=sorted(BASE_POLICIES), default="static", help="logging router's greedy choice")
    t_synth.add_argument("--policy-version", default="static-v1", help="logging policy version label")
    t_synth.add_argument("--shadow-bundle", help="PolicyBundleV1 directory Karmi runs in shadow for this batch")
    t_synth.add_argument("--trusted-public-key", help="hex Ed25519 public key trusted for --shadow-bundle")
    t_synth.add_argument("--karmi-version", default=MINIMUM_KARMI_VERSION)

    candidates = sub.add_parser("candidates", help="curate quarantined telemetry-derived evaluation candidates")
    csub = candidates.add_subparsers(dest="candidates_command", required=True)
    c_list = db(csub.add_parser("list", help="candidates with their current lifecycle state"))
    c_list.add_argument("--state")
    c_approve = db(csub.add_parser("approve", help="VALIDATED -> APPROVED -> role (explicit, audited)"))
    c_approve.add_argument("candidate_id")
    c_approve.add_argument("--role", required=True, choices=CANDIDATE_ROLES)
    operator(c_approve)
    c_reject = db(csub.add_parser("reject", help="reject a candidate"))
    c_reject.add_argument("candidate_id")
    operator(c_reject)

    prefs = sub.add_parser("preferences", help="high-confidence preference pairs from sanitized corrections")
    psub = prefs.add_subparsers(dest="preferences_command", required=True)
    p_extract = db(psub.add_parser("extract", help="classify corrections; only confident trainable pairs are PROPOSED"))
    p_extract.add_argument("--import-id")
    p_extract.add_argument("--min-confidence", type=float, default=0.8)
    p_list = db(psub.add_parser("list", help="pairs with lifecycle state (operator view)"))
    p_list.add_argument("--state")
    p_review = db(psub.add_parser("review", help="propose / approve / reject a pair"))
    p_review.add_argument("pair_id")
    p_review.add_argument("--decision", required=True, choices=("propose", "approve", "reject"))
    operator(p_review)
    p_export = db(psub.add_parser("export", help="write APPROVED pairs as JSONL and report DPO/PEFT readiness"))
    p_export.add_argument("--out", required=True)
    p_export.add_argument("--trainable-target", help="the trainable component a DPO/PEFT lane would target (none exists by default)")

    reward = sub.add_parser("reward", help="versioned multi-objective rewards")
    rsub = reward.add_subparsers(dest="reward_command", required=True)
    r_compute = db(rsub.add_parser("compute", help="compute + persist rewards for a telemetry run, an import (imp-...), 'all', or a benchmark run"))
    r_compute.add_argument("target")
    r_compute.add_argument("--reward-config", help="RewardConfig JSON (default: built-in provisional config)")
    r_compute.add_argument("--correction-category")

    r_dataset = db(router_sub.add_parser("dataset", help="build + persist a contextual-bandit dataset (live decisions with propensities)"))
    r_dataset.add_argument("--seed", type=int, required=True)
    r_dataset.add_argument("--import-id", action="append", help="restrict to these imports (repeatable; default all)")
    r_dataset.add_argument("--split", default="0.6,0.2,0.2", help="train,validation,holdout fractions")
    r_dataset.add_argument("--reward-config", help="RewardConfig JSON the rewards were computed with")
    r_train = db(router_sub.add_parser("train", help="train a LinUCB candidate (DRAFT -> TRAINED)"))
    r_train.add_argument("dataset_id")
    r_train.add_argument("--seed", type=int, required=True)
    r_train.add_argument("--alpha", type=float, default=0.0, help="UCB bonus in exported scores (default 0: greedy on theta)")
    r_train.add_argument("--lambda", type=float, default=1.0, dest="lambda_", help="ridge regularization")
    r_train.add_argument("--epsilon", type=float, default=0.05, help="exploration Karmi applies when running the policy")
    r_train.add_argument("--importance-weighting", action="store_true",
                         help="clipped 1/propensity weights (off by default: raised variance in ground-truth checks)")
    r_eval = db(router_sub.add_parser("evaluate", help="off-policy evaluation on the validation split vs logging/cheapest/flagship"))
    r_eval.add_argument("candidate_id")
    r_eval.add_argument("--seed", type=int, default=0)
    out(r_eval)
    r_bench = db(router_sub.add_parser("benchmark", help="SIMULATED core-benchmark evidence per synthetic action (for verify)"))
    r_bench.add_argument("--seed", type=int, default=7)
    out(r_bench, "write the action -> run_id mapping for verify --benchmark-runs")

    harness = sub.add_parser("harness", help="candidate-based harness prompt optimization")
    hsub = harness.add_subparsers(dest="harness_command", required=True)
    h_opt = db(hsub.add_parser("optimize", help="beam search over prompt candidates in the SIMULATED prompt-sensitive environment"))
    h_opt.add_argument("--rounds", type=int, default=4)
    h_opt.add_argument("--beam", type=int, default=3)
    h_opt.add_argument("--seed", type=int, default=0)

    verify = db(sub.add_parser("verify", help="run every promotion gate; TRAINED -> VERIFIED only if all hard gates pass"))
    verify.add_argument("candidate_id")
    verify.add_argument("--benchmark-runs", required=True, help="JSON mapping (or file) action -> graded core-benchmark run id")
    verify.add_argument("--config", help="VerifierConfig JSON, e.g. owner-approved tier_cost_ceiling_usd")
    verify.add_argument("--harness-candidate", help="also verify this harness candidate (SIMULATED holdout provider)")
    verify.add_argument("--report-dir", help="write the Evidence/Analysis/Decision report (json, md, html) here")
    out(verify)

    policy = sub.add_parser("policy", help="policy candidate lifecycle")
    posub = policy.add_subparsers(dest="policy_command", required=True)
    po_list = db(posub.add_parser("list", help="policy candidates with state"))
    po_list.add_argument("--kind", choices=("router", "harness"))
    po_approve = db(posub.add_parser("approve", help="VERIFIED -> APPROVED (human decision)"))
    po_approve.add_argument("candidate_id")
    operator(po_approve)
    po_report = db(posub.add_parser("report", help="render the latest verification report + compounding metrics"))
    po_report.add_argument("candidate_id")
    po_report.add_argument("--out", required=True, help="output directory")

    artifact = sub.add_parser("artifact", help="signed, immutable PolicyBundleV1 artifacts")
    asub = artifact.add_subparsers(dest="artifact_command", required=True)
    a_keygen = asub.add_parser("keygen", help="create an Ed25519 signing key (mode 0600, never overwritten)")
    a_keygen.add_argument("--path", help="default $PARAKH_SIGNING_KEY or ~/.config/parakh/signing_key.hex")
    a_export = db(asub.add_parser("export", help="APPROVED -> EXPORTED: write a read-only signed bundle"))
    a_export.add_argument("candidate_id")
    a_export.add_argument("--out", required=True, help="bundle root directory")
    a_export.add_argument("--key-path", help="signing key file (default as keygen)")
    a_export.add_argument("--actor", required=True)
    a_export.add_argument("--previous-compatible-version")
    a_verify = asub.add_parser("verify", help="signature, checksums, and no unlisted files")
    a_verify.add_argument("path")
    a_verify.add_argument("--trusted-public-key", required=True, action="append")
    a_karmi = asub.add_parser("karmi-check", help="load a bundle with the Karmi reference loader into a shadow candidate slot")
    a_karmi.add_argument("path")
    a_karmi.add_argument("--trusted-public-key", required=True, action="append")
    a_karmi.add_argument("--karmi-version", default=MINIMUM_KARMI_VERSION)
    a_karmi.add_argument("--known-action", action="append", help="Karmi model registry action ids (default: synthetic registry)")

    db(sub.add_parser("metrics", help="compounding flywheel metrics (denominators stated; missing data is null)"))


@contextmanager
def _evidence(path: str, *, create: bool = False) -> Generator[EvidenceStore, None, None]:
    if not create and not Path(path).is_file():
        raise NotFoundError(f"no evidence database at {path}")
    store = SQLiteStore(path)
    try:
        yield EvidenceStore(store)
    finally:
        store.close()


def _operator(args: argparse.Namespace) -> tuple[str, str]:
    actor, reason = (args.actor or "").strip(), (getattr(args, "reason", "") or "").strip()
    if not actor:
        raise ValidationError("a named --actor is required")
    if not reason and hasattr(args, "reason"):
        raise ValidationError("a non-blank --reason is required")
    return actor, reason


def _json_arg(value: str) -> Any:
    source = Path(value)
    return json.loads(source.read_text(encoding="utf-8") if source.is_file() else value)


def _reward_config(path: str | None) -> RewardConfig:
    return RewardConfig.from_dict(_json_arg(path)) if path else RewardConfig()


def _verifier_config(path: str | None) -> verifier.VerifierConfig:
    if not path:
        return verifier.VerifierConfig()
    raw = _json_arg(path)
    allowed = {f.name for f in dataclasses.fields(verifier.VerifierConfig)}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValidationError(f"unknown verifier config keys: {', '.join(unknown)}")
    if "critical_domains" in raw:
        raw["critical_domains"] = tuple(raw["critical_domains"])
    return verifier.VerifierConfig(**raw)


def _accepted_runs(evidence: EvidenceStore, import_id: str | None = None) -> list[RunRecord]:
    filters = {"status": "accepted", **({"import_id": import_id} if import_id else {})}
    runs = []
    for record in evidence.list("telemetry_records", **filters):
        raw = record["record"]
        parsed = parse_run(raw, record["index"], raw["feature_schema_version"])
        if not isinstance(parsed, RunRecord):
            raise IntegrityError(f"stored accepted run {record['run_id']} no longer parses: {parsed.reasons}")
        runs.append(parsed)
    return runs


def _emit(value: Any, path: str | None = None) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print_json(value)


def run(args: argparse.Namespace) -> int:
    handler = {"telemetry": _telemetry, "candidates": _candidates, "preferences": _preferences, "reward": _reward,
               "router": _router, "harness": _harness, "verify": _verify, "policy": _policy, "artifact": _artifact,
               "metrics": _metrics}[args.command]
    return handler(args)


def _telemetry(args: argparse.Namespace) -> int:
    if args.telemetry_command == "synthesize":
        shadow_policy: Callable[[Mapping[str, Any], Any], tuple[str, float]] | None = None
        shadow_version = None
        if args.shadow_bundle:
            if not args.trusted_public_key:
                raise ValidationError("--shadow-bundle requires --trusted-public-key")
            try:
                loaded = karmi.load_bundle(args.shadow_bundle, trusted_public_keys=[args.trusted_public_key], karmi_version=args.karmi_version,
                                           known_actions=synthetic.MODEL_BY_ACTION, expected_feature_schema_version=FEATURE_SCHEMA_VERSION)
            except karmi.BundleRejected as exc:
                raise ValidationError(f"shadow bundle rejected by the Karmi reference loader: {exc}") from exc
            rng = random.Random(f"shadow:{args.seed}:{args.batch_index}")

            def shadow(context: Mapping[str, Any], eligible: Any) -> tuple[str, float]:
                decision = loaded.select(context, list(eligible), rng, shadow=True)
                if decision is None:  # Karmi falls back to its static router when the candidate cannot score
                    return synthetic.static_policy(context, eligible), 1.0
                return decision["selected_action"], decision["selection_probability"]
            shadow_policy, shadow_version = shadow, loaded.version
        batch = synthetic.generate_batch(seed=args.seed, batch_index=args.batch_index, runs=args.runs, epsilon=args.epsilon,
                                         logging_policy_version=args.policy_version, base_policy=BASE_POLICIES[args.base_policy],
                                         shadow_policy=shadow_policy, shadow_policy_version=shadow_version)
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(batch, sort_keys=True) + "\n", encoding="utf-8")
        print_json({"path": str(target), "batch_id": batch["batch_id"], "runs": len(batch["runs"]), "evidence_class": "SIMULATED",
                    "producer": batch["producer"], "shadow_policy_version": shadow_version})
        return 0
    with _evidence(args.db, create=args.telemetry_command == "import") as evidence:
        if args.telemetry_command == "import":
            print_json(dataclasses.asdict(import_batch(evidence.store, Path(args.batch), source_label=args.source_label)))
            return 0
        imports = evidence.list("telemetry_imports") if not args.import_id else [evidence.get("telemetry_imports", args.import_id)]
        rows = []
        for imp in imports:
            quarantined = evidence.list("telemetry_records", import_id=imp["import_id"], status="quarantined")
            reasons = Counter(reason for record in quarantined for reason in record.get("reasons", []))
            rows.append({key: imp.get(key) for key in ("import_id", "batch_id", "batch_checksum", "producer_repo", "producer_version",
                                                       "generated_at", "record_count", "accepted", "quarantined", "candidates")}
                        | {"quarantine_reasons": dict(sorted(reasons.items()))})
        print_json(rows)
        return 0


def _candidates(args: argparse.Namespace) -> int:
    with _evidence(args.db) as evidence:
        if args.candidates_command == "list":
            print_json(list_candidates(evidence, state=args.state))
            return 0
        actor, reason = _operator(args)
        if args.candidates_command == "approve":
            print_json(approve_candidate(evidence, args.candidate_id, args.role, actor=actor, reason=reason))
        else:
            print_json(reject_candidate(evidence, args.candidate_id, actor=actor, reason=reason))
        return 0


def _preferences(args: argparse.Namespace) -> int:
    with _evidence(args.db) as evidence:
        if args.preferences_command == "extract":
            pairs = extract_pairs(evidence, _accepted_runs(evidence, args.import_id), min_confidence=args.min_confidence)
            print_json({"pairs": len(pairs), "by_state": dict(sorted(Counter(p["approval_state"] for p in pairs).items())),
                        "by_category": dict(sorted(Counter(p["category"] for p in pairs).items()))})
        elif args.preferences_command == "list":
            states = evidence.states("preference_pair")
            pairs = [{**p, "state": states.get(p["pair_id"])} for p in evidence.list("preference_pairs")]
            print_json([p for p in pairs if args.state is None or p["state"] == args.state])
        elif args.preferences_command == "review":
            actor, reason = _operator(args)
            print_json(review(evidence, args.pair_id, args.decision, actor=actor, reason=reason))
        else:
            count = export_approved(evidence, args.out)
            print_json({"exported": count, "path": args.out, "readiness": readiness(evidence, trainable_target=args.trainable_target)})
        return 0


def _reward(args: argparse.Namespace) -> int:
    config = _reward_config(args.reward_config)
    with _evidence(args.db) as evidence:
        target = args.target
        if target == "all" or target.startswith("imp-") or evidence.list("telemetry_records", run_id=target):
            if target == "all":
                runs = _accepted_runs(evidence)
            elif target.startswith("imp-"):
                runs = _accepted_runs(evidence, target)
            else:
                runs = [r for r in _accepted_runs(evidence) if r.run_id == target]
                if not runs:
                    raise ValidationError(f"telemetry run {target} is quarantined; quarantined runs never receive rewards")
            if not runs:
                raise NotFoundError(f"no accepted telemetry runs for {target}")
            records = [reward_for_run(run, config, correction_category=args.correction_category) for run in runs]
            subject = "telemetry_run"
        else:
            store = evidence.store
            store.get_run(target)
            grades = {g.attempt_id: g for g in store.list_grades(target)}
            reviews: dict[str, list[Any]] = {}
            for item in store.list_reviews(target):
                reviews.setdefault(item.case_id, []).append(item)
            records = [reward_for_attempt(a, grades[a.attempt_id], reviews.get(a.case_id), config)
                       for a in store.list_attempts(target) if a.attempt_id in grades]
            subject = "benchmark_attempt"
        for record in records:
            persist_reward(evidence, record)
        excluded = Counter(r.excluded_reason for r in records if r.scalar is None)
        print_json({"subject_type": subject, "computed": len(records), "schema_version": REWARD_SCHEMA_VERSION,
                    "config_hash": config.config_hash(), "provisional_config": config.provisional,
                    "excluded": dict(sorted(excluded.items())),
                    "mean_scalar": (sum(r.scalar for r in records if r.scalar is not None) / max(1, len(records) - sum(excluded.values())))
                    if len(records) > sum(excluded.values()) else None})
        return 0


def _router(args: argparse.Namespace) -> int:
    with _evidence(args.db) as evidence:
        if args.router_command == "dataset":
            config_hash = _reward_config(args.reward_config).config_hash()
            import_ids = args.import_id or [imp["import_id"] for imp in evidence.list("telemetry_imports")]
            observations = [o for i in import_ids for o in evidence.list("router_observations", import_id=i)]
            rewards = {r["subject_id"]: r for r in evidence.list("rewards", subject_type="telemetry_run", schema_version=REWARD_SCHEMA_VERSION)
                       if r["config_hash"] == config_hash}
            parts = [float(x) for x in args.split.split(",")]
            if len(parts) != 3:
                raise ValidationError("--split needs three fractions: train,validation,holdout")
            fractions = (parts[0], parts[1], parts[2])
            dataset = build_dataset(observations, rewards, feature_schema_version=FEATURE_SCHEMA_VERSION, reward_schema_version=REWARD_SCHEMA_VERSION,
                                    seed=args.seed, split=fractions, source={"import_ids": sorted(import_ids), "reward_config_hash": config_hash})
            if not dataset.examples:
                raise ValidationError(f"no usable examples (exclusions: {dataset.metadata['exclusions']}); compute rewards first")
            persist_dataset(evidence, dataset)
            print_json({"dataset_id": dataset.dataset_id, "checksum": dataset.checksum, "counts_by_split": dataset.metadata["counts_by_split"],
                        "exclusions": dataset.metadata["exclusions"], "actions": dataset.metadata["actions"],
                        "policy_versions": dataset.metadata["policy_versions"]})
        elif args.router_command == "train":
            dataset = load_dataset(evidence, args.dataset_id)
            if not dataset.examples_for("train"):
                raise ValidationError(f"dataset {args.dataset_id} has no training examples")
            hyperparameters = {"alpha": args.alpha, "lambda_": args.lambda_, "epsilon": args.epsilon,
                               "importance_weighting": args.importance_weighting}
            candidate_id, model = train_candidate(evidence, dataset, hyperparameters=hyperparameters, seed=args.seed, git=git_state())
            print_json({"candidate_id": candidate_id, "dataset_id": dataset.dataset_id, "algorithm": "linucb", "hyperparameters": hyperparameters,
                        "per_action_examples": {a: p["n"] for a, p in model.parameters.items()},
                        "state": evidence.state("policy_candidate", candidate_id)})
        elif args.router_command == "evaluate":
            candidate = evidence.get("policy_candidates", args.candidate_id)
            if candidate.get("kind") != "router":
                raise ValidationError(f"{args.candidate_id} is not a router candidate")
            dataset = load_dataset(evidence, candidate["dataset_id"])
            validation = list(dataset.examples_for("validation"))
            if not validation:
                raise ValidationError(f"dataset {dataset.dataset_id} has no validation examples")
            registry = verifier.registry_for(evidence, dataset)
            policy = LinUCBPolicy(from_policy_document(candidate["policy"]))
            comparison = replay.compare([policy, cheapest(registry), flagship(registry)], validation, seed=args.seed)
            body = {"policy_candidate_id": args.candidate_id, "dataset_id": dataset.dataset_id, "split": "validation", "seed": args.seed,
                    "comparison": comparison,
                    "paired_vs_logging": off_policy.paired_difference(policy, validation, margin=0.02, seed=args.seed)}
            report_id = "ope-" + stable_hash(body)[:20]
            if not evidence.exists("ope_reports", report_id):
                evidence.append("ope_reports", report_id, {"report_id": report_id, **body})
            _emit({"report_id": report_id, **body}, args.out)
        else:
            registry = verifier.registry_for_imports(evidence, [imp["import_id"] for imp in evidence.list("telemetry_imports")])
            actions = sorted(f"{m['provider']}/{m['model']}" for m in registry)
            real = [a for a in actions if a not in synthetic.MODEL_BY_ACTION]
            if real:
                raise ValidationError(f"no simulated evidence exists for real models {real}: run an authorized pilot "
                                      "(model-lab pilot run --allow-paid) and pass its graded run ids to verify")
            suite = load_core_suite()
            runs = {action: run_simulated_evidence(evidence.store, suite, action, seed=args.seed) for action in actions}
            _emit(runs, args.out)
        return 0


def _simulated_harness_provider(cases: Any) -> PromptSensitiveProvider:
    outputs, skills = simulated_task(cases)
    return PromptSensitiveProvider(outputs=outputs, skills=skills)


def _harness(args: argparse.Namespace) -> int:
    with _evidence(args.db, create=True) as evidence:
        suite = load_core_suite()
        provider = _simulated_harness_provider(optimizer_cases(suite, ("train", "validation")))
        result = optimize(PromptRegistry(evidence), evidence, suite, provider, rounds=args.rounds, beam=args.beam, seed=args.seed)
        print_json({"best_candidate_id": result.best.candidate_id, "baseline_candidate_id": result.baseline.candidate_id,
                    "validation_pass_rate": {"best": result.validation.get(result.best.candidate_id),
                                             "baseline": result.validation.get(result.baseline.candidate_id)},
                    "candidates_evaluated": len(result.validation), "holdout_evaluated": result.holdout_evaluated,
                    "evidence_class": "SIMULATED"})
        return 0


def _verify(args: argparse.Namespace) -> int:
    runs = _json_arg(args.benchmark_runs)
    if not isinstance(runs, dict) or not runs:
        raise ValidationError("--benchmark-runs must be a non-empty JSON object mapping action -> run id")
    config = _verifier_config(args.config)
    with _evidence(args.db) as evidence:
        report = verifier.verify(evidence, args.candidate_id, benchmark_runs=runs, config=config,
                                 harness_candidate_id=args.harness_candidate,
                                 harness_provider=_simulated_harness_provider if args.harness_candidate else None)
        if args.report_dir:
            write_optimization_report(report, args.report_dir, compounding_metrics(evidence))
        summary = {"report_id": report["report_id"], "passed": report["passed"], "failed_gates": report["failed_gates"],
                   "state": evidence.state("policy_candidate", args.candidate_id), "evidence_class": report["evidence_class"],
                   "gates": [{"gate": g["gate"], "passed": g["passed"], "reason": g["reason"]} for g in report["hard_gates"]],
                   "limitations": report["limitations"]}
        _emit(summary, args.out)
        return 0 if report["passed"] else 2


def _policy(args: argparse.Namespace) -> int:
    with _evidence(args.db) as evidence:
        if args.policy_command == "list":
            states = evidence.states("policy_candidate")
            rows = [{"candidate_id": c["candidate_id"], "kind": c["kind"], "parent_id": c.get("parent_id"),
                     "dataset_id": c.get("dataset_id"), "state": states.get(c["candidate_id"])}
                    for c in evidence.list("policy_candidates", **({"kind": args.kind} if args.kind else {}))]
            print_json(rows)
        elif args.policy_command == "approve":
            actor, reason = _operator(args)
            print_json(verifier.approve(evidence, args.candidate_id, actor=actor, reason=reason))
        else:
            reports = evidence.list("verification_reports", policy_candidate_id=args.candidate_id)
            if not reports:
                raise NotFoundError(f"{args.candidate_id} has no verification report")
            paths = write_optimization_report(reports[-1], args.out, compounding_metrics(evidence))
            print_json({key: str(path) for key, path in paths.items()})
        return 0


def _artifact(args: argparse.Namespace) -> int:
    if args.artifact_command == "keygen":
        print_json(signer.generate_key(args.path))
        return 0
    if args.artifact_command == "verify":
        errors = bundle.verify(args.path, args.trusted_public_key)
        print_json({"path": args.path, "verified": not errors, "errors": errors})
        return 0 if not errors else 2
    if args.artifact_command == "karmi-check":
        try:
            loaded = karmi.load_bundle(args.path, trusted_public_keys=args.trusted_public_key, karmi_version=args.karmi_version,
                                       known_actions=args.known_action or list(synthetic.MODEL_BY_ACTION),
                                       expected_feature_schema_version=FEATURE_SCHEMA_VERSION)
        except karmi.BundleRejected as exc:
            print_json({"path": args.path, "accepted": False, "reason": str(exc)})
            return 2
        slots = karmi.PolicySlots()
        slots.stage(loaded)
        slots.shadow()
        print_json({"path": args.path, "accepted": True, "artifact_version": loaded.version, "karmi_mode": slots.mode,
                    "karmi_active_policy": slots.active, "events": slots.events})
        return 0
    actor, _ = _operator(args)
    secret = signer.load_private(args.key_path)
    with _evidence(args.db) as evidence:
        print_json(bundle.export(evidence, args.candidate_id, out_root=args.out, secret=secret, git=git_state(), actor=actor,
                                 previous_compatible_version=args.previous_compatible_version))
    return 0


def _metrics(args: argparse.Namespace) -> int:
    with _evidence(args.db) as evidence:
        print_json(compounding_metrics(evidence))
    return 0
