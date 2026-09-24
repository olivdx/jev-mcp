# jev-mcp

An MCP server that turns Cursor's "I think I'm done" into a checked decision.
The agent summarizes work in `decide.extra`; optional test output can be attached.
It asks [TypeSafe Jev](https://docs.typesafe.ai/introduction)
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
| `decide(goal, extra?, tests?, profile?)` | Agent summary + test report → Jev → `fix` / `ask` / `done` |
| `health(project_root?, probe?)` | Key source and TypeSafe probe |
| `describe()` | Question set, policy, workflow, and `extra` hints |

### Recommended workflow

1. Agent runs tests locally (shell), then writes `decide.extra` with `summary` and `verification` (`exit_code`, `summary`, optional log tail).
2. Call **`decide`** with the user's goal and that `extra` object (or pass the same fields in `tests`).
3. Obey the verdict — `fix` keeps working, `ask` goes to the user, `done` may finish.

## Profiles

| Profile | Behavior |
|---------|----------|
| `default` | The nine policy rules as written |
| `strict` | Also asks when code changed with no test signal, or when Jev's cross-check confidently disagrees with a `done` |
| `ci` | `done` requires agent-reported tests with `exit_code` 0 |

## Headless gate

```bash
jev-mcp gate --goal "add retry" --extra-json '{"summary":"...","verification":{"exit_code":0}}' --json
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
tests:
  default_timeout_s: 600
  projects:
    - match: "pyproject.toml"
      command: ["poetry", "run", "pytest", "-q"]
jev:
  model: jev-latest
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
