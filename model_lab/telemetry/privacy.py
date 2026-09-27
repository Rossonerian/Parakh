"""Privacy validation and PII/credential detection for telemetry runs.

Best-effort privacy detection and redaction for incoming telemetry. Note that
detection is best-effort, not a guarantee of complete PII or secret removal.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

# Sensitive dict keys whose non-empty values are treated as credentials
CREDENTIAL_KEYS = frozenset({
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "cookie",
    "set-cookie",
})

# Precompiled regex patterns
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9_-]+ )?PRIVATE KEY-----",
    re.MULTILINE,
)

AUTH_HEADER_RE = re.compile(
    r"\bBearer\s+[a-zA-Z0-9_\-\.~+/]+=*",
)

JWT_RE = re.compile(
    r"\beyJ[a-zA-Z0-9_\-]{8,}\.eyJ[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]*\b",
)

SECRET_TOKEN_RE = re.compile(
    r"\b(?:sk-(?:live-|proj-)?[a-zA-Z0-9_\-]{16,}|sk-[a-zA-Z0-9_\-]{16,}|AKIA[0-9A-Z]{16}|ghp_[0-9a-zA-Z]{16,}|xox[baprs]-[0-9a-zA-Z-]{10,})\b",
)

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)

PAN_RE = re.compile(
    r"(?<![a-zA-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![a-zA-Z0-9])",
)

CARD_RE = re.compile(
    r"(?<![a-zA-Z0-9])(?:\d[ -]?){13,19}(?![a-zA-Z0-9])",
)

AADHAAR_RE = re.compile(
    r"(?<![a-zA-Z0-9])(?:\d{4}[ -]\d{4}[ -]\d{4}|\d{12})(?![a-zA-Z0-9])",
)

PHONE_RE = re.compile(
    r"(?<![a-zA-Z0-9])(?:\+\d{1,3}[-.\s]?)?(?:\(?\d{2,5}\)?[-.\s]?)?\d{2,5}[-.\s]?\d{3,5}(?![a-zA-Z0-9])",
)


def _luhn_valid(digits: str) -> bool:
    nums = [int(c) for c in digits]
    checksum = 0
    reverse = nums[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _scan_string(text: str) -> tuple[str, list[str]]:
    reasons: list[str] = []
    spans: list[tuple[int, int, str]] = []

    def add_span(start: int, end: int, reason: str) -> None:
        # Check if already covered by an existing span
        for s_start, s_end, _ in spans:
            if not (end <= s_start or start >= s_end):
                return
        spans.append((start, end, reason))
        reasons.append(reason)

    # 1. PEM private keys
    for m in PRIVATE_KEY_RE.finditer(text):
        add_span(m.start(), m.end(), "private_key")

    # 2. Authorization header
    for m in AUTH_HEADER_RE.finditer(text):
        add_span(m.start(), m.end(), "authorization_header")

    # 3. JWT
    for m in JWT_RE.finditer(text):
        add_span(m.start(), m.end(), "jwt")

    # 4. Secret tokens
    for m in SECRET_TOKEN_RE.finditer(text):
        add_span(m.start(), m.end(), "secret_token")

    # 5. Email
    for m in EMAIL_RE.finditer(text):
        add_span(m.start(), m.end(), "pii_email")

    # 6. PAN
    for m in PAN_RE.finditer(text):
        add_span(m.start(), m.end(), "pii_pan")

    # 7. Card numbers with Luhn check
    for m in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            add_span(m.start(), m.end(), "pii_card")

    # 8. Aadhaar
    for m in AADHAAR_RE.finditer(text):
        add_span(m.start(), m.end(), "pii_aadhaar")

    # 9. Phone numbers (>= 10 digits)
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) >= 10:
            add_span(m.start(), m.end(), "pii_phone")

    if not spans:
        return text, reasons

    # Replace from back to front
    spans.sort(key=lambda s: s[0], reverse=True)
    redacted_text = text
    for start, end, reason in spans:
        redacted_text = f"{redacted_text[:start]}[REDACTED:{reason}]{redacted_text[end:]}"

    return redacted_text, reasons


@dataclass(frozen=True)
class PrivacyResult:
    status: str
    reasons: tuple[str, ...]
    redacted: Any


def scan(value: Any) -> PrivacyResult:
    """Recursively scan data for secrets and PII, returning clean or rejected with redacted value."""
    all_reasons: list[str] = []

    def _walk(val: Any) -> Any:
        if isinstance(val, str):
            redacted_str, reasons = _scan_string(val)
            all_reasons.extend(reasons)
            return redacted_str
        if isinstance(val, Mapping):
            out_dict: dict[str, Any] = {}
            for k, v in val.items():
                if isinstance(k, str) and k.lower() in CREDENTIAL_KEYS and v not in (None, "", {}, [], ()):
                    all_reasons.append("credential_field")
                    out_dict[k] = "[REDACTED:credential_field]"
                else:
                    out_dict[k] = _walk(v)
            return out_dict
        if isinstance(val, list):
            return [_walk(item) for item in val]
        if isinstance(val, tuple):
            return tuple(_walk(item) for item in val)
        return val

    redacted = _walk(value)
    unique_reasons = tuple(sorted(set(all_reasons)))
    status = "rejected" if unique_reasons else "clean"
    return PrivacyResult(status=status, reasons=unique_reasons, redacted=redacted)
