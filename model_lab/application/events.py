"""Structured operational events: the durable trace the TUI and operators read.

Every event passes through ``redact`` before it is stored, so provider error
strings can never persist API keys or bearer tokens into the event log.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from model_lab.schemas import RunEvent
from model_lab.storage.sqlite import SQLiteStore

MAX_TEXT = 500
_SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|AUTH)", re.IGNORECASE)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password)\s*[=:]\s*[^\s&,;]+"),
)
REDACTED = "[REDACTED]"


def event_time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(text: str | None) -> str | None:
    """Remove credential-looking substrings and bound the length."""
    if text is None:
        return None
    for name, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_ENV.search(name) and value in text:
            text = text.replace(value, REDACTED)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def record_event(store: SQLiteStore, event_type: str, message: str, **fields: Any) -> int:
    """Append one event; text fields are redacted and bounded."""
    for name in ("error", "artifact"):
        if fields.get(name) is not None:
            fields[name] = redact(str(fields[name]))
    return store.add_event(RunEvent(timestamp=event_time(), event_type=event_type, message=redact(message) or "", **fields))
