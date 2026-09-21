from __future__ import annotations

import json
import logging
import sys
import uuid

from jev_mcp.util.redact import redact_text

logger = logging.getLogger("jev_mcp")

_format = "text"
_redact = True


def configure(level: str = "info", log_format: str = "text", redact: bool = True) -> None:
    """Send structured events to stderr; stdout belongs to the stdio MCP transport."""
    global _format, _redact
    _format = log_format
    _redact = redact
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False


def new_request_id() -> str:
    return str(uuid.uuid4())


def trace(event: str, **fields: object) -> None:
    clean: dict[str, object] = {}
    for key, value in fields.items():
        if value is None:
            continue
        clean[key] = redact_text(value) if _redact and isinstance(value, str) else value
    if _format == "json":
        logger.info(json.dumps({"event": event, **clean}, default=str))
        return
    rendered = " ".join(f"{key}={value}" for key, value in clean.items())
    logger.info("%s %s", event, rendered)
