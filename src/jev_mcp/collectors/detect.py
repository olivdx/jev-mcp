from __future__ import annotations

import json
from pathlib import Path

from jev_mcp.config import TestsConfig

_PYTHON_MARKERS = ("pyproject.toml", "pytest.ini", "setup.cfg")


def detect_test_command(project_root: Path, cfg: TestsConfig) -> tuple[str, list[str]] | None:
    """Return (runner_id, argv) for the first rule that matches, or None."""
    for rule in cfg.projects:
        if (project_root / rule.match).exists():
            return f"config:{rule.match}", list(rule.command)

    if any((project_root / marker).exists() for marker in _PYTHON_MARKERS):
        if (project_root / "poetry.lock").exists():
            return "pytest", ["poetry", "run", "pytest", "-q"]
        return "pytest", ["pytest", "-q"]

    manifest_path = project_root / "package.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
        scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
        if isinstance(scripts, dict) and scripts.get("test"):
            return "npm", ["npm", "test"]

    makefile = project_root / "Makefile"
    if makefile.exists():
        for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("test:"):
                return "make", ["make", "test"]

    return None
