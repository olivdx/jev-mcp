# Task 1 — Project scaffold

**Deliverable:** An installable Poetry package whose `jev-mcp --version` works.

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/jev_mcp/__init__.py`
- Create: `src/jev_mcp/cli/__init__.py`, `src/jev_mcp/cli/main.py`, `src/jev_mcp/cli/serve.py`
- Create: `src/jev_mcp/mcp/__init__.py`, `src/jev_mcp/mcp/transport.py`, `src/jev_mcp/mcp/server.py`
- Create: `tests/test_packaging.py`

**Interfaces:**
- Produces: `jev_mcp.cli.main:app` (Typer app named `jev-mcp`), `jev_mcp.mcp.transport.Transport`, `jev_mcp.mcp.server.run_server`.

---

- [ ] **Step 1: Write the failing test**

```python
# tests/test_packaging.py
import importlib.metadata


def test_distribution_version_is_available():
    assert importlib.metadata.version("mcp-jev-mcp")


def test_cli_app_is_named_jev_mcp():
    from jev_mcp.cli.main import app

    assert app.info.name == "jev-mcp"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `poetry install`

Expected: FAIL — there is no `pyproject.toml` yet, so Poetry itself errors out. That is the red state for this task.

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[tool.poetry]
name = "mcp-jev-mcp"
version = "0.1.0"
description = "MCP engineering control layer: git and test signals judged by TypeSafe Jev"
authors = ["1hoodlabs"]
license = "MIT"
readme = "README.md"
packages = [{ include = "jev_mcp", from = "src" }]
keywords = ["mcp", "typesafe", "jev", "cursor", "ai"]
classifiers = [
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "License :: OSI Approved :: MIT License",
  "Operating System :: OS Independent",
]

[tool.poetry.dependencies]
python = ">=3.11,<4"
typer = { extras = ["all"], version = "^0.15" }
mcp = ">=1.6,<2"
pyyaml = "^6.0"
typesafe-sdk = "^0.7"
uvicorn = "^0.30"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.24"
ruff = "^0.6"

[tool.poetry.scripts]
jev-mcp = "jev_mcp.cli.main:app"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
src = ["src"]
```

- [ ] **Step 4: Create the package skeleton**

```python
# src/jev_mcp/__init__.py
__version__ = "0.1.0"
```

```python
# src/jev_mcp/cli/__init__.py
```

```python
# src/jev_mcp/mcp/__init__.py
```

```python
# src/jev_mcp/mcp/transport.py
from enum import Enum


class Transport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"
```

```python
# src/jev_mcp/mcp/server.py
from __future__ import annotations

from jev_mcp.mcp.transport import Transport


def run_server(
    host: str | None = None,
    port: int | None = None,
    transport: Transport = Transport.STDIO,
) -> None:
    # Wired to FastMCP in task 11.
    raise NotImplementedError("MCP server is implemented in task 11")
```

```python
# src/jev_mcp/cli/serve.py
from __future__ import annotations

from typing import Annotated

import typer

from jev_mcp.mcp.server import run_server
from jev_mcp.mcp.transport import Transport


def serve_cmd(
    transport: Annotated[
        Transport,
        typer.Option(help="MCP transport: stdio for clients, http for local debugging"),
    ] = Transport.STDIO,
    host: Annotated[str | None, typer.Option(help="Bind host (http only)")] = None,
    port: Annotated[int | None, typer.Option(help="Bind port (http only)")] = None,
) -> None:
    """Start the MCP server."""
    run_server(host=host, port=port, transport=transport)
```

```python
# src/jev_mcp/cli/main.py
from __future__ import annotations

import importlib.metadata
from typing import Annotated

import typer

from jev_mcp.cli.serve import serve_cmd


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(importlib.metadata.version("mcp-jev-mcp"))
        raise typer.Exit()


app = typer.Typer(name="jev-mcp", help="jev-mcp - AI engineering control layer for MCP clients")


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show installed version and exit",
        ),
    ] = None,
) -> None:
    """Collect repository signals, ask TypeSafe Jev, and return a typed verdict."""


app.command("serve")(serve_cmd)


if __name__ == "__main__":
    app()
```

```gitignore
.venv/
dist/
build/
*.egg-info/
__pycache__/
.pytest_cache/
.ruff_cache/
credentials.yaml
```

- [ ] **Step 5: Create a minimal README so Poetry can build**

```markdown
# jev-mcp

MCP engineering control layer. Collects git and test signals, asks TypeSafe Jev,
and returns a typed `fix` | `ask` | `done` verdict.

Full documentation lands in task 13.
```

- [ ] **Step 6: Install and run the test**

Run: `poetry install && poetry run pytest tests/test_packaging.py -v`

Expected: 2 passed.

- [ ] **Step 7: Verify the console script**

Run: `poetry run jev-mcp --version`

Expected: `0.1.0`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml poetry.lock .gitignore src tests README.md
git commit -m "chore: scaffold jev-mcp package and CLI entrypoint"
```
