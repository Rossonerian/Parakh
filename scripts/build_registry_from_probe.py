#!/usr/bin/env python3
"""Turn a capped probe result + catalog snapshot into a provisional model-registry.v1 file.

Honest limits baked in: only task types that were actually measured get a score; a model needs at
least one successful reply to be listed; the capability class is a size-based provisional label
(the probe's cases are too easy to discriminate); data terms stay ``unknown`` (so notes never reach
these models).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model_lab.providers.registry import build_model_registry, build_shortlist_per_class  # noqa: E402

# Provisional, size/capability-based classes from the model names; revisit after the full pilot.
CLASS_BY_MODEL = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": "advanced",
    "nvidia/nemotron-3-super-120b-a12b:free": "advanced",
    "google/gemma-4-31b-it:free": "balanced",
    "google/gemma-4-26b-a4b-it:free": "balanced",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": "balanced",
    "poolside/laguna-xs-2.1:free": "balanced",
    "poolside/laguna-s-2.1:free": "balanced",
    "cohere/north-mini-code:free": "balanced",
    "liquid/lfm-2.5-2.6b:free": "economy",
    "nvidia/nemotron-3.5-lightning:free": "economy",
}
CATEGORY_KEY = {"maths": "maths", "hindi": "hindi", "code": "code", "mixed": "mixed", "study": "study"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    catalog = {m["id"]: m for m in json.loads(args.catalog.read_text(encoding="utf-8"))}
    by_model: dict[str, list[dict]] = {}
    for row in probe["rows"]:
        by_model.setdefault(row["model_id"], []).append(row)

    evaluations = []
    skipped = {}
    for model_id, rows in by_model.items():
        if not any(r.get("ok") for r in rows):
            skipped[model_id] = "no successful reply in the probe"
            continue
        scores: dict[str, list[float]] = {}
        for row in rows:
            scores.setdefault(CATEGORY_KEY[row["category"]], []).append(1.0 if row.get("passed") else 0.0)
        meta = catalog[model_id]
        evaluations.append({
            "model_id": model_id,
            "provider": "openrouter",
            "context_length": meta["context_length"],
            "class": CLASS_BY_MODEL.get(model_id, "economy"),
            "scores": {k: sum(v) / len(v) for k, v in scores.items()},
            "data_terms": "unknown",
            "supports_structured_output": any(
                p in meta["supported_parameters"] for p in ("response_format", "structured_outputs")
            ),
        })
    registry = build_model_registry(evaluations, snapshot_date=args.date, provisional=True)
    registry["notes"] = (
        "Provisional capped probe (maths + hindi, 1 case each, 1 repeat). Classes are size-based; "
        "data terms unknown so private notes are never routed here. Skipped models: "
        + json.dumps(skipped, sort_keys=True)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"listed": len(evaluations), "skipped": skipped,
                      "shortlist": build_shortlist_per_class(registry, top_n=2)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
