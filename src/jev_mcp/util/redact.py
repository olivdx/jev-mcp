from __future__ import annotations

import re

PLACEHOLDER = "<REDACTED>"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b[A-Z0-9_]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_]*\b"
        r"\s*[:=]\s*[\"']?[^\s\"',]{6,}"
    ),
)


def redact_text(text: str) -> str:
    """Replace well-known secret shapes before text reaches Jev or the logs."""
    cleaned = text
    for pattern in _PATTERNS:
        cleaned = pattern.sub(PLACEHOLDER, cleaned)
    return cleaned
