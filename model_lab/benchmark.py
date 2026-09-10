"""Benchmark loading, validation, inspection, and candidate export."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .errors import ValidationError
from .schemas import Case, Evaluation, Limits, Provenance, RubricCriterion, Suite


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object")
    return value


def case_from_dict(raw: dict[str, Any]) -> Case:
    raw = _object(raw, "case")
    required = {"case_id", "family_id", "split", "complexity_level", "domain", "language", "tags", "messages", "evaluation", "fixture_policy", "suite_version", "provenance", "limits"}
    missing = sorted(required - raw.keys())
    if missing:
        raise ValidationError(f"missing required case fields: {', '.join(missing)}")
    evaluation = _object(raw["evaluation"], "evaluation")
    rubric_raw = evaluation.get("rubric")
    if not isinstance(rubric_raw, list):
        raise ValidationError("evaluation.rubric must be an array")
    rubric = tuple(RubricCriterion(str(item.get("criterion", "")), item.get("weight", 1.0)) for item in rubric_raw if isinstance(item, dict))
    if len(rubric) != len(rubric_raw):
        raise ValidationError("each rubric item must be an object")
    evaluation_obj = Evaluation(
        method=evaluation.get("method", ""),
        reference_answer=evaluation.get("reference_answer"),
        rubric=rubric,
        critical_failures=tuple(evaluation.get("critical_failures", [])),
    )
    provenance = _object(raw["provenance"], "provenance")
    limits = _object(raw["limits"], "limits")
    messages = raw["messages"]
    if not isinstance(messages, list):
        raise ValidationError("messages must be an array")
    return Case(
        case_id=raw["case_id"],
        family_id=raw["family_id"],
        split=raw["split"],
        complexity_level=raw["complexity_level"],
        domain=raw["domain"],
        language=raw["language"],
        tags=tuple(raw["tags"]),
        messages=tuple(dict(message) for message in messages),
        evaluation=evaluation_obj,
        fixture_policy=raw["fixture_policy"],
        suite_version=raw["suite_version"],
        provenance=Provenance(**provenance),
        limits=Limits(**limits),
    )


def load_suite(path: str | Path) -> Suite:
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"benchmark file does not exist: {file_path}")
    cases: list[Case] = []
    raw_lines: list[str] = []
    try:
        with file_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                raw_lines.append(line.rstrip("\n"))
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
                try:
                    cases.append(case_from_dict(value))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValidationError(f"invalid case on line {line_number}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValidationError(f"benchmark is not UTF-8: {file_path}") from exc
    if not cases:
        raise ValidationError("benchmark contains no cases")
    suite_versions = {case.suite_version for case in cases}
    if len(suite_versions) != 1:
        raise ValidationError("benchmark contains multiple suite versions")
    source_hash = hashlib.sha256(("\n".join(raw_lines) + "\n").encode("utf-8")).hexdigest()
    return Suite(next(iter(suite_versions)), tuple(cases), str(file_path), source_hash)


def validate_suite(suite: Suite) -> dict[str, Any]:
    counts = {"cases": len(suite.cases), "families": len({c.family_id for c in suite.cases}), "domains": len({c.domain for c in suite.cases}), "splits": {split: sum(c.split == split for c in suite.cases) for split in sorted({c.split for c in suite.cases})}, "complexity": {str(level): sum(c.complexity_level == level for c in suite.cases) for level in range(1, 5)}}
    family_levels: dict[str, set[int]] = {}
    for case in suite.cases:
        family_levels.setdefault(case.family_id, set()).add(case.complexity_level)
    return {"suite_version": suite.suite_version, "source_hash": suite.source_hash, **counts, "family_level_counts": {k: sorted(v) for k, v in sorted(family_levels.items())}}


def select_cases(suite: Suite, *, case_ids: Iterable[str] | None = None, splits: Iterable[str] | None = None, domains: Iterable[str] | None = None, workflows: Iterable[str] | None = None, complexity_levels: Iterable[int] | None = None) -> tuple[Case, ...]:
    wanted_ids = set(case_ids or ())
    wanted_splits = set(splits or ())
    wanted_domains = set(domains or ())
    wanted_workflows = set(workflows or ())
    wanted_levels = set(complexity_levels or ())
    selected = tuple(case for case in suite.cases if (not wanted_ids or case.case_id in wanted_ids) and (not wanted_splits or case.split in wanted_splits) and (not wanted_domains or case.domain in wanted_domains) and (not wanted_workflows or case.family_id in wanted_workflows) and (not wanted_levels or case.complexity_level in wanted_levels))
    unknown = wanted_ids - set(suite.case_ids)
    if unknown:
        raise ValidationError(f"unknown case IDs: {', '.join(sorted(unknown))}")
    if not selected:
        raise ValidationError("case selection is empty")
    return selected


def export_candidate_jsonl(suite: Suite, path: str | Path, cases: Iterable[Case] | None = None) -> int:
    selected = tuple(cases or suite.cases)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        for case in selected:
            stream.write(json.dumps(case.candidate_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return len(selected)

