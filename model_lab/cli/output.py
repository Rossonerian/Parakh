"""User-facing rendering helpers for CLI output."""

from __future__ import annotations

import json
from typing import Any


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


__all__ = ["print_json"]
