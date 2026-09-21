from __future__ import annotations

SCHEMA_VERSION = "1.0"


def tool_response(
    body: dict,
    *,
    request_id: str,
    duration_ms: int,
    errors: list[dict] | None = None,
) -> dict:
    """Wrap a tool body in the common envelope every jev-mcp response carries."""
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "duration_ms": duration_ms,
        "errors": errors or [],
        **body,
    }
