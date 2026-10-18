"""Registry builder for model_registry.v1 consumed by Karmi."""

from __future__ import annotations

from collections.abc import Mapping
import time
from typing import Any

VALID_CLASSES = ("economy", "balanced", "advanced")
VALID_DATA_TERMS = ("unknown", "no_training", "training_on_prompts")
REQUIRED_SCORE_KEYS = ("code", "maths", "study", "hindi", "mixed", "summary")


def determine_model_class(context_length: int, scores: Mapping[str, float]) -> str:
    """Classify model into economy, balanced, or advanced based on context length and score."""
    measured = [scores[k] for k in REQUIRED_SCORE_KEYS if k in scores]
    avg_score = sum(measured) / len(measured) if measured else 0.0
    if context_length >= 65536 and avg_score >= 0.70:
        return "advanced"
    if context_length >= 16384 and avg_score >= 0.50:
        return "balanced"
    return "economy"


def build_model_registry(
    model_evaluations: list[dict[str, Any]],
    *,
    snapshot_date: str | None = None,
    provisional: bool = True,
) -> dict[str, Any]:
    """Turn scored results into model-registry.v1 format."""
    date_str = snapshot_date or time.strftime("%Y-%m-%d")
    models_list: list[dict[str, Any]] = []

    for item in model_evaluations:
        model_id = item["model_id"]
        provider = item.get("provider", "openrouter")
        context_length = int(item.get("context_length", 32768))
        raw_scores = item.get("scores", {})
        # Only measured task types are emitted; an unmeasured key is absent, never invented as 0.
        scores = {k: float(raw_scores[k]) for k in REQUIRED_SCORE_KEYS if k in raw_scores}

        assigned_class = item.get("class") or determine_model_class(context_length, scores)
        if assigned_class not in VALID_CLASSES:
            raise ValueError(f"invalid model class: {assigned_class}")

        data_terms = item.get("data_terms", "unknown")
        if data_terms not in VALID_DATA_TERMS:
            data_terms = "unknown"

        # unknown means private_data_allowed is strictly false
        private_data_allowed = False if data_terms == "unknown" else bool(item.get("private_data_allowed", False))

        models_list.append({
            "model_id": model_id,
            "provider": provider,
            "class": assigned_class,
            "prompt_price_usd": "0",
            "completion_price_usd": "0",
            "context_length": context_length,
            "private_data_allowed": private_data_allowed,
            "data_terms": data_terms,
            "supports_structured_output": bool(item.get("supports_structured_output", False)),
            "scores": scores,
            "score_status": "provisional" if provisional else "verified",
        })

    return {
        "schema_version": "model-registry.v1",
        "snapshot_date": date_str,
        "provisional": provisional,
        "models": models_list,
    }


def build_shortlist_per_class(
    registry: dict[str, Any],
    *,
    top_n: int = 1,
) -> dict[str, list[str]]:
    """Build a shortlist of top candidate model IDs per capability class."""
    classes: dict[str, list[tuple[float, str]]] = {
        "economy": [],
        "balanced": [],
        "advanced": [],
    }

    for model in registry.get("models", []):
        m_cls = model.get("class", "economy")
        scores = model.get("scores", {})
        avg_score = sum(scores.values()) / max(len(scores), 1)
        m_id = model["model_id"]
        if m_cls in classes:
            classes[m_cls].append((avg_score, m_id))

    shortlist: dict[str, list[str]] = {}
    for cls_name, candidates in classes.items():
        candidates.sort(key=lambda x: x[0], reverse=True)
        shortlist[cls_name] = [m_id for _, m_id in candidates[:top_n]]

    return shortlist
