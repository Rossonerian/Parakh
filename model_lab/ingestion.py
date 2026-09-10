"""Safe JSON/JSONL/CSV attempt ingestion with quarantine instead of overwrite."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import IntegrityError, ValidationError
from .schemas import Attempt, AttemptStatus, MetricKind, ModelConfig, utc_now
from .storage import SQLiteStore


@dataclass(frozen=True)
class IngestionResult:
    imported: int
    quarantined: int
    duplicates: int


def _attempt(record: dict[str, Any], run_id: str, expected_model: ModelConfig | None = None) -> Attempt:
    required = {"attempt_id", "case_id", "prompt_hash", "response_text"}
    missing = sorted(required - record.keys())
    if missing:
        raise ValidationError("missing import fields: " + ", ".join(missing))
    model_data = record.get("model_config") or ({"provider": record.get("provider"), "model": record.get("model")} if record.get("provider") and record.get("model") else None)
    if model_data is None:
        if expected_model is None:
            raise ValidationError("provider/model metadata is required")
        model = expected_model
    else:
        model = ModelConfig(**model_data)
    if expected_model and (model.provider != expected_model.provider or model.model != expected_model.model):
        raise ValidationError("provider/model metadata mismatch")
    status = AttemptStatus(record.get("status", "success"))
    return Attempt(attempt_id=record["attempt_id"], run_id=run_id, logical_request_id=record.get("logical_request_id", record["attempt_id"]), case_id=record["case_id"], model_config=model, prompt_hash=record["prompt_hash"], response_text=record.get("response_text"), status=status, started_at=record.get("started_at", utc_now()), completed_at=record.get("completed_at", utc_now()), finish_reason=record.get("finish_reason"), error=record.get("error"), first_token_latency_ms=record.get("first_token_latency_ms"), completion_latency_ms=record.get("completion_latency_ms"), input_tokens=record.get("input_tokens"), output_tokens=record.get("output_tokens"), cost_minor=record.get("cost_minor"), currency=record.get("currency"), metric_kinds={k: MetricKind(v) for k, v in record.get("metric_kinds", {}).items()}, raw_metadata=dict(record.get("raw_metadata", {})))


def ingest_records(store: SQLiteStore, run_id: str, records: list[dict[str, Any]], *, source_label: str = "import", expected_model: ModelConfig | None = None) -> IngestionResult:
    imported = quarantined = duplicates = 0
    run = store.get_run(run_id)
    valid_cases = set(run.case_ids)
    for record in records:
        try:
            attempt = _attempt(record, run_id, expected_model)
            if attempt.case_id not in valid_cases:
                raise ValidationError("case ID is not part of run")
            store.add_attempt(attempt, raw_record=record)
            imported += 1
        except IntegrityError:
            duplicates += 1
            store.quarantine(source_label, "duplicate attempt", record, utc_now())
            quarantined += 1
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            store.quarantine(source_label, str(exc), record, utc_now())
            quarantined += 1
    return IngestionResult(imported, quarantined, duplicates)


def ingest_file(store: SQLiteStore, run_id: str, path: str | Path, *, fmt: str | None = None, source_label: str = "import", expected_model: ModelConfig | None = None) -> IngestionResult:
    source = Path(path)
    fmt = (fmt or source.suffix.lstrip(".")).lower()
    try:
        if fmt == "jsonl":
            records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        elif fmt == "json":
            value = json.loads(source.read_text(encoding="utf-8"))
            records = value if isinstance(value, list) else value.get("attempts", []) if isinstance(value, dict) else []
        elif fmt == "csv":
            with source.open(newline="", encoding="utf-8") as stream:
                records = list(csv.DictReader(stream))
        else:
            raise ValidationError("format must be jsonl, json, or csv")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error, AttributeError, TypeError) as exc:
        raise ValidationError(f"cannot parse import: {exc}") from exc
    if not isinstance(records, list):
        raise ValidationError("import must contain an array of records")
    return ingest_records(store, run_id, records, source_label=source_label, expected_model=expected_model)
