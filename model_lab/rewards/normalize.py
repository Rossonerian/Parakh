"""Cost and latency normalization according to tier envelopes and SLOs.

Normalizes raw resource measurements against configured budget envelopes and
latency targets without currency conversion or metric fabrication.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from model_lab.rewards.schema import RewardConfig


def normalize_cost(
    cost: float | None,
    currency: str | None,
    tier: str,
    config: RewardConfig,
) -> float | None:
    """Normalize USD cost against tier envelope, capped at config.cost_cap.

    Returns None if cost is None, non-finite, currency is missing, or currency != 'USD'.
    Never converts non-USD currencies.
    """
    if cost is None or currency is None or currency != "USD":
        return None
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        return None

    envelope = config.cost_envelope_per_request.get(
        tier,
        config.cost_envelope_per_request.get("default", 0.01),
    )
    if envelope <= 0:
        return config.cost_cap

    normalized = float(cost) / envelope
    return min(normalized, config.cost_cap)


def normalize_latency(
    latency_ms: float | None,
    routing_context: Mapping[str, Any] | None,
    config: RewardConfig,
) -> float | None:
    """Normalize completion latency against SLA/SLO, capped at config.latency_cap.

    Returns None if latency_ms is None or non-finite.
    """
    if latency_ms is None:
        return None
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)) or not math.isfinite(latency_ms) or latency_ms < 0:
        return None

    slo = None
    if routing_context is not None and isinstance(routing_context, Mapping):
        slo = routing_context.get("latency_slo_ms")

    if slo is None or isinstance(slo, bool) or not isinstance(slo, (int, float)) or slo <= 0:
        slo = config.default_latency_slo_ms

    normalized = float(latency_ms) / float(slo)
    return min(normalized, config.latency_cap)
