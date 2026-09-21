# jev-mcp Implementation Plan — Overview

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Each task lives in its own file in this directory and ends with an independently testable deliverable. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship a production MCP server plus CLI that collects Git and test signals, asks TypeSafe Jev atomic questions, and returns a typed `fix` | `ask` | `done` verdict for Cursor and for headless CI gates.

**Architecture:** Poetry package `jev_mcp` that mirrors ai-router's **packaging shell only** (Typer CLI, FastMCP stdio/http, thin `server.py`, `AppState`, coded errors). Domain layers: `collectors/` produce deterministic facts, `jev/` talks to TypeSafe, `decision/` owns the routing rules. Tools are stateless: the caller passes the `collect_git` and `run_tests` payloads into `decide`.

**Tech stack:** Python `>=3.11,<4`, Poetry, `mcp`, `typer`, `pyyaml`, `typesafe-sdk ^0.7`, `uvicorn`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-09-21-jev-mcp-design.md`

---

## Global constraints

Every task inherits these. Values are copied verbatim from the spec.

- PyPI name `mcp-jev-mcp`; console script `jev-mcp`; import package `jev_mcp`.
- Python `>=3.11,<4`.
- `typesafe-sdk = "^0.7"` (0.7.0 is current; requires Python ≥3.10, pulls `httpx2`, `pydantic`, `tenacity`).
- **Retries belong to the SDK.** Pass `typesafe_sdk.RetryPolicy(max_retries=...)`; never hand-roll a retry loop.
- API key precedence: env `TYPESAFE_API_KEY`, then `<JEV_MCP_HOME>/credentials.yaml`, else `NOT_CONFIGURED`.
- `JEV_MCP_HOME` defaults to `~/.jev-mcp` and is what the test suite overrides for isolation.
- Key management is CLI-only: `jev-mcp key add|status|remove`. No MCP tool ever returns or accepts a key.
- MCP tools: `collect_git`, `run_tests`, `decide`, `health`, `describe`.
- Every tool response carries `schema_version` `"1.0"`, `request_id`, `duration_ms`, `errors`.
- Question set id `engineering-gate-v2`; policy id `policy-engineering-gate-v2`; profiles `default`, `strict`, `ci`.
- **Noul answers carry no confidence.** Where policy needs certainty for a Noul it uses decisiveness `abs(noul - 0.5) * 2`.
- **Score returns a float from 0 to `len(criteria) - 1`**, a probability-weighted mean. Compare the normalized value `score / (len(criteria) - 1)`.
- Policy decides the action; the `next_action` Choice is a logged cross-check only.
- Subprocesses run through an argv vector; never `shell=True`.
- Gate exit codes: `done` 0, `fix` 1, `ask` 2, tool error 3.
- Comments in code are written in English.

---

## Task order

Each task depends only on the ones before it.

| # | File | Deliverable |
|---|------|-------------|
| 1 | `task-01-scaffold.md` | Installable package, `jev-mcp --version` |
| 2 | `task-02-foundation.md` | `errors`, `logger`, `util/paths`, `util/redact`, `util/responses` |
| 3 | `task-03-config.md` | `config.py` with YAML + env overrides |
| 4 | `task-04-credentials-key-cli.md` | `credentials.py` and `jev-mcp key add\|status\|remove` |
| 5 | `task-05-proc.md` | `util/proc.py` argv subprocess with output caps |
| 6 | `task-06-collect-git.md` | `collectors/git.py` with per-file diff budgeting |
| 7 | `task-07-detect-runner.md` | `collectors/detect.py` + `collectors/runner.py` |
| 8 | `task-08-jev-questions-state.md` | `jev/questions.py`, `jev/answers.py`, `jev/state_builder.py` |
| 9 | `task-09-jev-client.md` | `jev/client.py` with SDK error mapping |
| 10 | `task-10-policy.md` | `decision/policy.py`, `decision/envelope.py`, golden matrix |
| 11 | `task-11-mcp-tools-server.md` | `mcp/tools.py`, `mcp/server.py`, five live tools |
| 12 | `task-12-cli-gate.md` | `jev-mcp gate` with exit codes |
| 13 | `task-13-readme-ci.md` | README, CI workflow, wheel smoke |

---

## Final file map

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Poetry metadata, script, ruff, pytest |
| `src/jev_mcp/__init__.py` | Version constant |
| `src/jev_mcp/errors.py` | `JevMcpError` and typed subclasses |
| `src/jev_mcp/logger.py` | Text/JSON events, `request_id` |
| `src/jev_mcp/config.py` | Config dataclasses, YAML + env merge |
| `src/jev_mcp/credentials.py` | Key resolve, save, remove, verify |
| `src/jev_mcp/util/paths.py` | `JEV_MCP_HOME`, project root resolution |
| `src/jev_mcp/util/redact.py` | Secret scrubbing |
| `src/jev_mcp/util/responses.py` | Tool response envelope |
| `src/jev_mcp/util/proc.py` | Async argv subprocess, output caps |
| `src/jev_mcp/collectors/git.py` | Git snapshot |
| `src/jev_mcp/collectors/detect.py` | Test command detection |
| `src/jev_mcp/collectors/runner.py` | Test execution |
| `src/jev_mcp/jev/questions.py` | `engineering-gate-v2` definitions |
| `src/jev_mcp/jev/answers.py` | `SystemOneResponse` → `JevAnswers` |
| `src/jev_mcp/jev/state_builder.py` | State assembly + redaction |
| `src/jev_mcp/jev/client.py` | `AsyncTypeSafeClient` + error mapping |
| `src/jev_mcp/decision/policy.py` | Facts, rules, profiles, confidence |
| `src/jev_mcp/decision/envelope.py` | `decide` payload shaping |
| `src/jev_mcp/mcp/transport.py` | stdio/http enum |
| `src/jev_mcp/mcp/tools.py` | `AppState` + `handle_*` |
| `src/jev_mcp/mcp/server.py` | FastMCP registration |
| `src/jev_mcp/cli/main.py` | Typer root |
| `src/jev_mcp/cli/serve.py` | `serve` |
| `src/jev_mcp/cli/key.py` | `key add\|status\|remove` |
| `src/jev_mcp/cli/gate.py` | Headless pipeline |
| `tests/conftest.py` | Home isolation, git repo fixture, app state |
| `tests/test_*.py` | One module per task |
| `README.md` | Install, Cursor config, tools, security |
| `.github/workflows/ci.yml` | ruff, pytest, wheel smoke |

---

## Cross-task interface contract

These names are fixed. A task that consumes them must not rename them.

```python
# errors.py
class JevMcpError(Exception):
    code: str
    message: str

# util/paths.py
def jev_home() -> Path
def config_path() -> Path
def credentials_path() -> Path
def resolve_project_root(raw: str) -> Path

# util/responses.py
SCHEMA_VERSION: str = "1.0"
def tool_response(body: dict, *, request_id: str, duration_ms: int, errors: list[dict] | None = None) -> dict

# util/proc.py
@dataclass(frozen=True)
class ProcResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float
    truncated: bool

class CommandNotFoundError(Exception): ...
async def run_argv(cmd: list[str], cwd: Path, *, timeout_s: float, max_output_bytes: int,
                   env: dict[str, str] | None = None) -> ProcResult

# config.py
AppConfig(host, port, log_level, log_format, log_redact, git, tests, jev, decision)
GitConfig(max_diff_bytes, max_file_diff_bytes, max_stat_files)
TestsConfig(default_timeout_s, max_output_bytes, env_allowlist, projects)
TestProjectRule(match, command)
JevConfig(model, request_timeout_s, max_retries)
DecisionConfig(default_profile, thresholds)
Thresholds(goal_ambiguous_ask, tests_blocking_fix, goal_addressed_min,
           incomplete_work_fix, scope_creep_ask, risk_high_normalized,
           crosscheck_min_confidence)
def load_config(path: Path | None = None, *, use_user_file: bool = True) -> AppConfig

# credentials.py
def resolve_api_key(*, path: Path | None = None) -> tuple[str | None, str]
def save_api_key(api_key: str, *, path: Path | None = None) -> Path
def remove_api_key(*, path: Path | None = None) -> bool
def mask(api_key: str) -> str
def verify_api_key(api_key: str) -> None

# collectors
async def collect_git(project_root: Path, cfg: GitConfig, *, base_ref: str | None = None,
                      staged_only: bool = False, max_diff_bytes: int | None = None) -> dict
def detect_test_command(project_root: Path, cfg: TestsConfig) -> tuple[str, list[str]] | None
async def run_tests(project_root: Path, cfg: TestsConfig, *, command: list[str] | None = None,
                    timeout_s: float | None = None, env: dict[str, str] | None = None) -> dict

# jev
QUESTIONSET_ID: str = "engineering-gate-v2"
def build_questions() -> dict[str, object]
@dataclass(frozen=True) class ChoiceAnswer: choice: str; confidence: float; probabilities: dict[str, float]
@dataclass(frozen=True) class ScoreAnswer: score: float; confidence: float; top_level: int; probabilities: dict[int, float]
@dataclass(frozen=True) class JevAnswers: model: str; nouls: dict[str, float]; choices: dict[str, ChoiceAnswer]; scores: dict[str, ScoreAnswer]
def normalize_response(response, questions: dict) -> JevAnswers
def build_state(*, goal: str, git: dict | None = None, tests: dict | None = None,
                extra: dict | None = None) -> tuple[dict, list[str]]
async def evaluate_state(state: dict, cfg: AppConfig, api_key: str) -> JevAnswers

# decision
POLICY_ID: str = "policy-engineering-gate-v2"
PROFILES: tuple[str, ...] = ("default", "strict", "ci")
@dataclass(frozen=True) class Facts: diff_empty: bool; tests_ran: bool; tests_exit_code: int | None; tests_timed_out: bool
@dataclass(frozen=True) class DecideResult: action: str; confidence: float; reasons: list[str]; policy_trace: list[str]
def facts_from_payloads(git: dict | None, tests: dict | None) -> Facts
def route_decision(answers: JevAnswers, *, facts: Facts, profile: str,
                   cfg: DecisionConfig, missing_signals: list[str]) -> DecideResult
def build_decide_payload(result: DecideResult, answers: JevAnswers, *, model: str,
                         missing_signals: list[str]) -> dict

# mcp/tools.py
@dataclass class AppState: config: AppConfig
def create_app_state(config: AppConfig | None = None) -> AppState
async def handle_collect_git(state, *, project_root, base_ref=None, staged_only=False,
                             max_diff_bytes=None, mcp_session_id=None) -> dict
async def handle_run_tests(state, *, project_root, command=None, timeout_s=None,
                           env=None, mcp_session_id=None) -> dict
async def handle_decide(state, *, goal, git=None, tests=None, project_root=None,
                        profile=None, extra=None, mcp_session_id=None) -> dict
async def handle_health(state, *, project_root=None, probe=False, mcp_session_id=None) -> dict
async def handle_describe(state, *, mcp_session_id=None) -> dict
```

---

## Execution handoff

Two ways to run this plan:

1. **Subagent-driven (recommended)** — one fresh subagent per task file, review between tasks.
2. **Inline** — execute in the current session with checkpoints after tasks 4, 7, 10, and 13.
