# Task 13 — README, CI, and release smoke

**Deliverable:** Documentation that gets a new developer from zero to a working Cursor connection, plus a CI pipeline that is required to pass.

**Files:**
- Modify: `README.md`
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the finished CLI and MCP surface.
- Produces: no code; this task is the release gate.

---

- [ ] **Step 1: Write the README**

Replace the placeholder from task 1 with these sections. Keep the tone factual and the commands copy-pasteable.

````markdown
# jev-mcp

An MCP server that turns Cursor's "I think I'm done" into a checked decision.
It collects git and test signals, asks [TypeSafe Jev](https://docs.typesafe.ai/introduction)
a set of narrow questions, and returns a typed verdict: **fix**, **ask**, or **done**.

The routing decision is made by policy code in this repository. Jev answers atomic
questions about the state; it does not choose the action.

| | Name |
|---|---|
| PyPI | `mcp-jev-mcp` |
| CLI | `jev-mcp` |

## Quick start

```bash
pipx install mcp-jev-mcp
jev-mcp key add <YOUR_TYPESAFE_API_KEY>
jev-mcp key status
```

Then add the MCP server to Cursor (`~/.cursor/mcp.json` or the project's `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "jev-mcp": {
      "type": "stdio",
      "command": "jev-mcp",
      "args": ["serve"]
    }
  }
}
```

Reload MCP in Cursor, then ask the agent to call `health`.

## Requirements

- Python 3.11 or newer
- `git` on PATH
- A TypeSafe API key

## API key

Resolution order:

1. `TYPESAFE_API_KEY` in the environment — use this in CI.
2. `<JEV_MCP_HOME>/credentials.yaml`, written by `jev-mcp key add`.

`JEV_MCP_HOME` defaults to `~/.jev-mcp`.

```bash
jev-mcp key add <API_KEY>   # verifies against TypeSafe, then stores
jev-mcp key status            # source plus a masked hint, never the key
jev-mcp key remove
```

On Linux and macOS the file is written with mode `0600`. On Windows it is protected
only by your user profile ACL, so prefer the environment variable on a shared machine.

## MCP tools

| Tool | What it does |
|------|--------------|
| `collect_git(project_root, base_ref?, staged_only?, max_diff_bytes?)` | Branch, changed files, and a diff budgeted per file so no hunk is cut in half |
| `run_tests(project_root, command?, timeout_s?)` | Runs the detected or supplied test command; a non-zero exit code comes back as data |
| `decide(goal, git?, tests?, profile?, extra?)` | Asks Jev, applies policy, returns `fix` / `ask` / `done` with reasons |
| `health(project_root?, probe?)` | Key source, git availability, detected test command |
| `describe()` | The live question set, policy rules, and profiles |

The tools are stateless: pass the `collect_git` and `run_tests` payloads straight into `decide`.

### Recommended workflow

1. The agent implements the change.
2. `collect_git` and `run_tests`.
3. `decide` with the user's goal and both payloads.
4. Obey the verdict — `fix` keeps working, `ask` goes to the user, `done` may finish.

Add a project rule requiring step 4 before any completion claim.

## Profiles

| Profile | Behavior |
|---------|----------|
| `default` | The nine policy rules as written |
| `strict` | Also asks when code changed with no test signal, or when Jev's cross-check confidently disagrees with a `done` |
| `ci` | `done` requires a test run that exited zero |

## Headless gate

```bash
jev-mcp gate --goal "add retry to the uploader" --project-root . --profile ci --json
```

| Exit code | Meaning |
|-----------|---------|
| 0 | done |
| 1 | fix |
| 2 | ask |
| 3 | tool error |

Usable from a pre-push hook or a CI job.

## Configuration

`<JEV_MCP_HOME>/config.yaml`, with environment variables taking precedence.
See `docs/superpowers/specs/2026-09-21-jev-mcp-design.md` section 4 for every field.

```yaml
git:
  max_diff_bytes: 524288
  max_file_diff_bytes: 65536
tests:
  default_timeout_s: 600
  projects:
    - match: "pyproject.toml"
      command: ["poetry", "run", "pytest", "-q"]
jev:
  model: jev-1.13
  max_retries: 2
decision:
  default_profile: default
```

## Security

- The key never travels through an MCP tool; key management is CLI-only.
- Diffs and test output pass through a redactor before they reach Jev or the logs.
- Subprocesses run through an argument vector; there is no shell interpolation.
- Your diff and test output are sent to the TypeSafe API. Treat that as you would any
  third-party code analysis service, and read their terms.
- `serve --transport http` binds to localhost and has no authentication. It is for
  local debugging only.

## Development

```bash
poetry install
poetry run pytest -v
poetry run ruff check src tests
poetry run jev-mcp serve --transport http
```

## License

MIT
````

- [ ] **Step 2: Create the CI workflow**

```yaml
# .github/workflows/ci.yml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poetry
        run: pipx install poetry

      - name: Install dependencies
        run: poetry install

      - name: Lint
        run: poetry run ruff check src tests

      - name: Test
        run: poetry run pytest -v

  package:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        run: pipx install poetry

      - name: Build the wheel
        run: poetry build

      - name: Smoke test the wheel
        run: |
          python -m venv /tmp/smoke
          /tmp/smoke/bin/pip install dist/*.whl
          /tmp/smoke/bin/jev-mcp --version
          /tmp/smoke/bin/jev-mcp --help
```

- [ ] **Step 3: Run the full local verification**

Run:

```bash
poetry run ruff check src tests
poetry run pytest -v
poetry build
```

Expected: no lint findings, all tests pass, and a wheel plus sdist in `dist/`.

- [ ] **Step 4: Smoke the wheel locally**

On PowerShell, resolve the filename explicitly — the glob does not expand the way it does in bash:

```powershell
$wheel = (Get-ChildItem dist/mcp_jev_mcp-*.whl | Select-Object -First 1).FullName
python -m venv $env:TEMP\jev-smoke
& "$env:TEMP\jev-smoke\Scripts\pip.exe" install $wheel
& "$env:TEMP\jev-smoke\Scripts\jev-mcp.exe" --version
& "$env:TEMP\jev-smoke\Scripts\jev-mcp.exe" --help
```

On bash:

```bash
python -m venv /tmp/jev-smoke
/tmp/jev-smoke/bin/pip install dist/mcp_jev_mcp-*.whl
/tmp/jev-smoke/bin/jev-mcp --version
```

Expected: `0.1.0` and a help screen listing `serve`, `gate`, and `key`.

- [ ] **Step 5: Smoke the MCP server in Cursor**

1. Point `.cursor/mcp.json` at the local entry point: `"command": "poetry", "args": ["run", "jev-mcp", "serve"]` with `"cwd"` set to this repository, or install the wheel and use `jev-mcp`.
2. Reload MCP in Cursor.
3. Ask the agent to call `health`, then `describe`.

Expected: `health` reports `key_source` and `git_available: true`; `describe` lists seven questions and three profiles.

- [ ] **Step 6: Verify the acceptance criteria**

Walk section 15 of the spec and confirm each item. Every claim needs a command whose output you have actually seen.

| Criterion | Evidence |
|-----------|----------|
| Installable CLI | `jev-mcp --version` from the smoke venv |
| Key lifecycle | `key add` (mocked in tests), `key status`, `key remove` |
| Five MCP tools | `tests/test_mcp_server.py` plus the Cursor smoke |
| Gate exit codes | `tests/test_cli_gate.py` parametrized cases |
| Golden matrix and CI | `pytest -v` output and a green CI run |
| README in 10 minutes | Follow your own quick start on a clean machine or container |

- [ ] **Step 7: Commit**

```bash
git add README.md .github/workflows/ci.yml
git commit -m "docs: add README and CI pipeline with wheel smoke test"
```
