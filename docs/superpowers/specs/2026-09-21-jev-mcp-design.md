# jev-mcp — Design Specification

**Status:** Revision 2 (post-review)
**Date:** 2026-09-21
**Scope:** Production MCP server + CLI for AI engineering control in Cursor (and headless CI/hooks)

---

## 1. Purpose

**jev-mcp** is an MCP (Model Context Protocol) server that acts as an **AI engineering control layer** for Cursor and other MCP clients. It does not implement code changes itself. It:

1. Collects **deterministic signals** from the local repository (Git, test runners).
2. Sends a structured **state** plus **atomic** questions to [TypeSafe Jev](https://docs.typesafe.ai/introduction) (System One).
3. Applies **versioned policy in Python** to produce a typed verdict: **`fix`**, **`ask`**, or **`done`**, with a decision confidence and a policy trace.

Cursor remains the executor (edit files, run terminal, talk to the user). jev-mcp is the **control plane** that standardizes snapshots and structured decisions so agents do not rely on prose parsing or subjective "task complete" claims.

### 1.1 Decision ownership

The routing decision belongs to **code**, not to the model. Jev answers narrow questions about the state; `decision/policy.py` combines those answers with deterministic facts (test exit code, empty diff) and produces the action. A `next_action` Choice is still asked, but only as a **cross-check** that is logged when it disagrees with policy — never as the primary driver. This follows [how to build with System One](https://docs.typesafe.ai/concepts/how-to-build-with-system-one): decompose a composite judgment into atomic questions and weigh them in your own code.

### 1.2 Non-goals

- **Not** a browser or web-LLM router (no relationship to ai-router domain logic).
- **Not** a replacement for Cursor's built-in Git, test, or search tools — it **orchestrates and judges** using the same class of local operations.
- **Not** storing conversation history or patching code.

### 1.3 Reference architecture (borrowed from ai-router)

Only the **packaging and MCP skeleton** mirror [ai-router](https://github.com/scriptkid23/ai-router):

| Borrow | Do not borrow |
|--------|----------------|
| Poetry package layout `src/jev_mcp/` | Gemini/ChatGPT adapters, CloakBrowser |
| Typer CLI, `serve` with stdio/http | `ask`, page queue, provider registry |
| FastMCP thin `server.py` + `tools.py` handlers | Web session login |
| `AppState`, structured errors with codes | Browser automation |
| `~/.jev-mcp/config.yaml` + env overrides | Parallel ask to chat providers |
| pytest, ruff, PyPI/pipx distribution story | |

---

## 2. System context

```text
┌─────────────────────────────────────────────────────────────┐
│ Cursor (or other MCP client)                                 │
│  • implements fixes, runs user commands                      │
│  • calls jev-mcp tools in a defined gate workflow            │
└───────────────────────────────┬─────────────────────────────┘
                                │ stdio MCP
                                ▼
┌─────────────────────────────────────────────────────────────┐
│ jev-mcp                                                      │
│  collect_git │ run_tests │ decide │ health │ describe        │
│  collectors (deterministic) → Jev client → decision/policy   │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
                ▼                             ▼
         local git / subprocess          TypeSafe API (Jev)
```

Headless path (same handlers as MCP):

```text
jev-mcp gate --goal "..." --project-root ...
  → internally: collect_git + run_tests + decide
```

---

## 3. Distribution and CLI

### 3.1 Package

| Item | Value |
|------|--------|
| PyPI name | `mcp-jev-mcp` |
| Import package | `jev_mcp` |
| Console script | `jev-mcp` |
| Python | `>=3.11,<4` |
| Dependencies | `mcp>=1.6,<2`, `typer`, `pyyaml`, **`typesafe-sdk ^0.7`**, `uvicorn` |

`typesafe-sdk` 0.7.0 is the current release; it requires Python ≥3.10 and pulls in `httpx2`, `pydantic`, and `tenacity`. The SDK is pre-1.0, so the caret constraint `^0.7` resolves to `>=0.7.0,<0.8.0` and upgrades are a deliberate, tested step.

### 3.2 CLI commands

```text
jev-mcp --version
jev-mcp serve [--transport stdio|http] [--host] [--port]

jev-mcp key add <API_KEY>    # verify against TypeSafe, then persist
jev-mcp key status             # masked hint, source (file|env|none)
jev-mcp key remove             # delete local credentials file

jev-mcp gate \
  --goal TEXT \
  --project-root PATH \
  [--profile default|strict|ci] \
  [--base-ref REF] \
  [--test-command CMD] \
  [--no-tests] \
  [--json]
```

**Gate exit codes** (so git hooks and CI can branch without parsing JSON):

| Action | Exit code |
|--------|-----------|
| `done` | `0` |
| `fix` | `1` |
| `ask` | `2` |
| Tool error (`JevMcpError`) | `3` |

**Security:** API keys are **never** exposed through MCP tools. Key management is CLI-only.

### 3.3 API key and home directory resolution

Key precedence:

1. Environment variable **`TYPESAFE_API_KEY`** (wins over file — suitable for CI).
2. File **`<JEV_MCP_HOME>/credentials.yaml`** (written by `jev-mcp key add`).
3. Missing → operations requiring Jev raise **`NOT_CONFIGURED`** with remediation text.

**`JEV_MCP_HOME`** (default `~/.jev-mcp`) is the root for `config.yaml` and `credentials.yaml`. It exists so operators can relocate state and so the **test suite can isolate itself** from the developer's real credentials.

`key add` behavior:

- Trim input; reject empty (`INVALID_KEY`).
- **Verify** with `TypeSafeClient(api_key=...).models.list()` before persisting. Failures map to `INVALID_KEY` (401) or `API_UNREACHABLE` (connection/timeout) and **do not write** the file.
- Write atomically (temp file in the same directory, then `os.replace`).
- POSIX: `chmod 0600` on the file and `0700` on the directory. **Windows:** `chmod` is effectively a no-op, so `key add` prints a one-line warning that the file is protected only by the user profile ACL, and the README recommends `TYPESAFE_API_KEY` on shared machines.
- Never print the key; `key status` prints `source` plus a masked suffix (`…a1b2`).

---

## 4. Configuration

**Path:** `<JEV_MCP_HOME>/config.yaml`
**Env prefix:** `JEV_MCP_*`, plus `TYPESAFE_API_KEY`.

Every field below is implemented; nothing in this section is aspirational.

```yaml
schema_version: 1

host: 127.0.0.1
port: 8089

log_level: info          # debug|info|warn|error
log_format: text         # text|json
log_redact: true         # scrub secrets from log fields

git:
  max_diff_bytes: 524288       # total budget across all files
  max_file_diff_bytes: 65536   # per-file budget; files over it are summarized, not cut mid-hunk
  max_stat_files: 500          # cap on changed_files list length

tests:
  default_timeout_s: 600
  max_output_bytes: 262144
  env_allowlist: ["CI", "PATH", "HOME", "LANG"]
  projects:                     # ordered; first rule whose marker file exists wins
    - match: "pyproject.toml"
      command: ["poetry", "run", "pytest", "-q"]
    - match: "package.json"
      command: ["npm", "test"]

jev:
  model: jev-1.13
  request_timeout_s: 60
  max_retries: 2               # passed to typesafe_sdk.RetryPolicy

decision:
  default_profile: default
  thresholds:
    goal_ambiguous_ask: 0.6
    tests_blocking_fix: 0.6
    goal_addressed_min: 0.5
    incomplete_work_fix: 0.6
    scope_creep_ask: 0.7
    risk_high_normalized: 0.67  # normalized score (0..1) treated as "high risk"
    crosscheck_min_confidence: 0.5
```

**Retries are owned by the SDK.** `jev.max_retries` is passed to `typesafe_sdk.RetryPolicy`; jev-mcp does not implement its own retry loop, and does not attempt to override the SDK's retryable-status list.

Environment overrides: `JEV_MCP_HOME`, `JEV_MCP_HOST`, `JEV_MCP_PORT`, `JEV_MCP_LOG_LEVEL`, `JEV_MCP_LOG_FORMAT`, `JEV_MCP_LOG_REDACT`, `JEV_MCP_GIT_MAX_DIFF_BYTES`, `JEV_MCP_TESTS_TIMEOUT_S`, `JEV_MCP_JEV_MODEL`, `JEV_MCP_JEV_TIMEOUT_S`, `JEV_MCP_DEFAULT_PROFILE`.

---

## 5. MCP tools

Every tool response includes:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Response contract version (`"1.0"`) |
| `request_id` | string | UUID for correlation |
| `duration_ms` | number | Handler wall time |
| `errors` | array | `{ "code", "message" }` — non-fatal collector problems |

Fatal failures raise `JevMcpError`, which the MCP layer surfaces as `RuntimeError("[CODE] message")` (same convention as ai-router).

### 5.1 `collect_git`

**Purpose:** Deterministic Git snapshot for decision state.

| Param | Required | Description |
|-------|----------|-------------|
| `project_root` | yes | Path to repo (resolved; must exist) |
| `base_ref` | no | When set, diff is `<base_ref>...HEAD` plus working-tree changes; `merge_base_with` reports the merge base |
| `staged_only` | no | Default `false`; when `true`, diff is `--cached` |
| `max_diff_bytes` | no | Override config budget |

**Truncation is per file, never mid-hunk.** The collector lists changed files, then collects each file's diff in order. A file whose diff exceeds `max_file_diff_bytes`, or that does not fit in the remaining total budget, is **omitted whole** and recorded in `omitted_files` with its byte size. This keeps every hunk Jev sees syntactically intact.

**Payload:**

```json
{
  "branch": "main",
  "head_sha": "abc123",
  "is_clean": false,
  "changed_files": ["src/foo.py"],
  "untracked_files": ["notes.md"],
  "diff_stat": "...",
  "diff": "...",
  "truncated": false,
  "omitted_files": [{ "path": "poetry.lock", "bytes": 180422 }],
  "base_ref": null,
  "merge_base_with": null
}
```

Untracked files are listed by name only; their content is not diffed.

**Errors:** `PATH_INVALID`, `NOT_A_REPO`, `GIT_NOT_FOUND`, `GIT_FAILED`.

**Security:** `git` is invoked through an argument vector, never a shell string.

### 5.2 `run_tests`

| Param | Required | Description |
|-------|----------|-------------|
| `project_root` | yes | Repo root |
| `command` | no | Explicit argv list; overrides detection |
| `timeout_s` | no | Override config |
| `env` | no | Extra env; only keys in `tests.env_allowlist` are passed through |

**Detection order:** config `tests.projects` rules (first marker file that exists), then built-ins — `pyproject.toml`/`pytest.ini`/`setup.cfg` → pytest (prefixed with `poetry run` when `poetry.lock` exists), `package.json` with `scripts.test` → `npm test`, `Makefile` with a `test:` target → `make test`.

**A non-zero exit code is a signal, not an error.** It is returned in the payload so `decide` can use it. **A timeout is likewise a signal**: the runner is killed and the payload comes back with `timed_out: true` plus whatever output arrived, which policy rule 1 turns into `fix`. `TEST_RUNNER_FAILED` is raised only when the command cannot be launched at all (binary missing).

**Payload:**

```json
{
  "runner_id": "pytest",
  "command": ["poetry", "run", "pytest", "-q"],
  "exit_code": 1,
  "timed_out": false,
  "stdout": "...",
  "stderr": "...",
  "output_truncated": false,
  "duration_s": 12.3
}
```

**Errors:** `PATH_INVALID`, `NO_TEST_COMMAND`, `TEST_RUNNER_FAILED`.

### 5.3 `decide`

**Purpose:** Build Jev state, ask the versioned question set in **one** TypeSafe request, apply policy, return the verdict envelope.

| Param | Required | Description |
|-------|----------|-------------|
| `goal` | yes | User task / acceptance criteria |
| `git` | no | Payload from `collect_git` |
| `tests` | no | Payload from `run_tests` |
| `project_root` | no | Metadata for logging |
| `profile` | no | `default` \| `strict` \| `ci` |
| `extra` | no | `{ "files_touched": [], "notes": "" }` |

**Stateless:** the caller passes the blobs; the server keeps no session. This makes decisions replayable and auditable.

#### Question set `engineering-gate-v2`

All questions are atomic. Choice options and Score levels carry **situation descriptions**, not bare labels — the Score docs show that numeric or label-only criteria collapse confidence (`["0","1","2"]` scored 0.55 at confidence 0.33 where descriptive levels scored 0.0 at confidence 1.0).

| Key | Primitive | Asks |
|-----|-----------|------|
| `goal_addressed` | Noul | Does the diff implement what the goal describes? |
| `goal_ambiguous` | Noul | Is the goal too underspecified to verify from the diff? |
| `tests_blocking` | Noul | Does the test output show failures that block completion? |
| `incomplete_work` | Noul | Does the diff contain stubs, TODOs, debug prints, commented-out code? |
| `scope_creep` | Noul | Does the diff contain substantial changes unrelated to the goal? |
| `risk_regression` | Score | Blast radius of the change (4 levels) |
| `next_action` | Choice | Cross-check only: `fix` \| `ask_user` \| `done` |

#### Answer semantics

These follow the [Score](https://docs.typesafe.ai/primitives/score) and [Choice](https://docs.typesafe.ai/primitives/choice) contracts and must not be re-invented:

- **Noul** returns a single probability `0..1`. **It carries no confidence.** Where policy needs a notion of certainty for a Noul, it uses *decisiveness* = `abs(noul - 0.5) * 2`.
- **Score** returns a float from `0` to `len(criteria) - 1` — a probability-weighted mean, not an ordinal. `risk_regression` has four levels, so its range is `0.0..3.0`. Policy compares the **normalized** value `score / (len(criteria) - 1)`. Score also returns `probabilities`, `legend`, and `confidence`.
- **Choice** returns `choice`, `probabilities`, and `confidence`.

`risk_regression` levels (index 0–3):

| Level | Description |
|-------|-------------|
| 0 | Localized change; one module, low blast radius |
| 1 | Several modules or a visible behavioral surface |
| 2 | Broad change, or touches a critical path such as auth, payments, migrations |
| 3 | Likely breaking without strong test evidence |

#### Policy `policy-engineering-gate-v2`

Rules are evaluated in order; the first match wins. Deterministic facts are checked **before** any model answer.

| # | Condition | Action |
|---|-----------|--------|
| 1 | Tests ran and `timed_out` | `fix` |
| 2 | Tests ran and `exit_code != 0` | `fix` |
| 3 | `goal_ambiguous ≥ goal_ambiguous_ask` | `ask` |
| 4 | `tests_blocking ≥ tests_blocking_fix` | `fix` |
| 5 | `incomplete_work ≥ incomplete_work_fix` | `fix` |
| 6 | `goal_addressed < goal_addressed_min` | `fix` |
| 7 | `scope_creep ≥ scope_creep_ask` | `ask` |
| 8 | `normalized(risk_regression) ≥ risk_high_normalized` **and** tests did not run | `fix` |
| 9 | otherwise | `done` |

**Profile differences:**

| Profile | Behavior |
|---------|----------|
| `default` | Rules as written. Missing `git` or `tests` is recorded in `missing_signals` but does not by itself block `done`. |
| `strict` | Adds: a `done` result is downgraded to `ask` when the `next_action` cross-check disagrees at `confidence ≥ crosscheck_min_confidence`; a non-empty diff with no test signal yields `ask`. |
| `ci` | Adds: `done` requires tests to have run with `exit_code == 0`; otherwise `fix`. Missing `git` yields `fix`. |

**Decision confidence** is the certainty of the rule that fired, not a global model score:

- Deterministic rules (1, 2) → `1.0`.
- Noul rules (3–7) → decisiveness of that Noul.
- Score rule (8) → that Score's `confidence`.
- Rule 9 (`done`) → the minimum decisiveness across the Nouls that had to stay below their thresholds, which makes a `done` reached on weak evidence visibly low-confidence.

**Cross-check:** `next_action` is always recorded in `jev.answers`. When its mapped action differs from the policy action, `policy_trace` gains `crosscheck:disagree`, and in `strict` the downgrade above applies.

**Payload:**

```json
{
  "action": "fix",
  "confidence": 0.82,
  "jev": {
    "model": "jev-1.13",
    "questionset_id": "engineering-gate-v2",
    "policy_id": "policy-engineering-gate-v2",
    "answers": {}
  },
  "reasons": ["tests_blocking=0.91 >= 0.6"],
  "policy_trace": ["facts:tests_ran", "rule:tests_blocking", "route:fix"],
  "missing_signals": []
}
```

**Errors:** `NOT_CONFIGURED`, `AUTH_FAILED`, `JEV_RATE_LIMITED`, `JEV_TIMEOUT`, `API_UNREACHABLE`, `JEV_ERROR`, `INVALID_PROFILE`.

References: [primitives](https://docs.typesafe.ai/primitives), [confidence](https://docs.typesafe.ai/confidence), [composite scoring](https://docs.typesafe.ai/patterns/composite-scoring), [intent routing](https://docs.typesafe.ai/patterns/intent-routing).

### 5.4 `health`

| Param | Required | Description |
|-------|----------|-------------|
| `project_root` | no | When given, also reports git availability for that path |
| `probe` | no | Default `false`. When `true`, calls `models.list()` to check the API |

`probe` defaults to off because agents call `health` frequently and a network round-trip per call wastes rate limit.

```json
{
  "ok": true,
  "key_source": "file",
  "key_hint": "…a1b2",
  "typesafe_reachable": null,
  "git_available": true,
  "home": "/home/u/.jev-mcp",
  "config_path": "/home/u/.jev-mcp/config.yaml",
  "test_command": ["poetry", "run", "pytest", "-q"]
}
```

`typesafe_reachable` is `null` when `probe` is false.

### 5.5 `describe`

Returns the tool list, the question set, the policy rule table, profile differences, and the recommended workflow — **generated from the same constants the code uses** (`questions.py`, `policy.py`), never hand-maintained prose, so it cannot drift from behavior.

---

## 6. Recommended Cursor workflow

1. Agent implements the user's request.
2. Agent calls `collect_git` and `run_tests`.
3. Agent calls `decide` with the goal and both payloads.
4. Agent obeys the verdict: `fix` → keep working; `ask` → put the question to the user; `done` → may report completion.

A project rule or skill should require step 4 before any completion claim.

---

## 7. Internal module layout

```text
src/jev_mcp/
  __init__.py
  config.py              # yaml + env
  errors.py              # JevMcpError + typed subclasses
  logger.py              # text/json logging, request_id
  credentials.py         # key storage, resolution, verification
  util/
    paths.py             # JEV_MCP_HOME, project_root resolution
    redact.py            # secret scrubbing
    responses.py         # tool_response envelope
    proc.py              # argv-only async subprocess with output caps
  collectors/
    git.py
    detect.py            # test command detection
    runner.py            # test execution
  jev/
    questions.py         # engineering-gate-v2 definitions
    answers.py           # SystemOneResponse -> JevAnswers
    state_builder.py
    client.py            # AsyncTypeSafeClient + error mapping
  decision/
    policy.py            # rules, profiles, confidence
    envelope.py
  mcp/
    transport.py
    tools.py             # AppState + handle_*
    server.py            # FastMCP registration
  cli/
    main.py
    serve.py
    key.py
    gate.py
```

---

## 8. Error model

Base: `JevMcpError(code, message)`.

| Code | Source |
|------|--------|
| `NOT_CONFIGURED` | No API key |
| `INVALID_KEY` | `key add` rejected by API, or empty input |
| `AUTH_FAILED` | 401 during a tool call |
| `JEV_RATE_LIMITED` | 429 |
| `JEV_TIMEOUT` | Request timeout |
| `API_UNREACHABLE` | Connection failure |
| `JEV_ERROR` | Any other SDK/API failure |
| `PATH_INVALID` | `project_root` missing or not a directory |
| `NOT_A_REPO` | `collect_git` outside a work tree |
| `GIT_NOT_FOUND` | `git` not on PATH |
| `GIT_FAILED` | git exited non-zero |
| `NO_TEST_COMMAND` | No rule matched and no command given |
| `TEST_RUNNER_FAILED` | Runner binary could not be launched |
| `INVALID_PROFILE` | Unknown `profile` value |

**SDK exception mapping** (`typesafe_sdk`), applied in `jev/client.py`:

| SDK exception | Code |
|---------------|------|
| `TypeSafeAuthenticationError` | `AUTH_FAILED` |
| `TypeSafeRateLimitError` | `JEV_RATE_LIMITED` (message includes `retry_after_ms` when present) |
| `TypeSafeAPITimeoutError` | `JEV_TIMEOUT` |
| `TypeSafeAPIConnectionError` | `API_UNREACHABLE` |
| `TypeSafeAPIError` | `JEV_ERROR` (message includes `status`) |
| `TypeSafeError` | `JEV_ERROR` |

Ordering matters: `TypeSafeAPITimeoutError` subclasses `TypeSafeAPIConnectionError`, and the specific HTTP errors subclass `TypeSafeAPIError`, so handlers must be listed most-specific first.

---

## 9. Security and privacy

- **Secrets:** key only via env or `credentials.yaml`; never returned by an MCP tool. POSIX `0600`; on Windows the README directs shared-machine users to the env var.
- **Redaction:** diff and test output pass through `redact_text` before reaching Jev or the logs.
- **Subprocess:** argv only, no `shell=True`; test env limited to `tests.env_allowlist`.
- **HTTP debug:** binds `127.0.0.1`, no auth, documented as local-only.
- **Data sent to TypeSafe:** diffs and logs may contain proprietary code — the README states this plainly.

---

## 10. Observability

Structured events on stderr, `text` or `json` per `log_format`, each carrying `request_id` and, when present, the MCP session id header:

| Event | Fields |
|-------|--------|
| `tool_start` | `tool`, `request_id`, `mcp_session_id` |
| `tool_end` | `tool`, `request_id`, `duration_ms`, `error_code` |
| `git_collected` | `changed_files`, `diff_bytes`, `truncated` |
| `tests_ran` | `runner_id`, `exit_code`, `duration_s`, `timed_out` |
| `jev_request` | `model`, `questionset_id`, `state_bytes` |
| `policy_route` | `profile`, `rule`, `action`, `confidence` |

Diff and test bodies are never logged.

---

## 11. Testing strategy

| Layer | Coverage |
|-------|----------|
| Isolation | Autouse fixture points `JEV_MCP_HOME` at `tmp_path` for the whole suite, so no test can read or delete the developer's real key or config |
| `collect_git` | Temp repos, per-file omission, not-a-repo, base_ref |
| `detect` / `runner` | Marker-file matrix, config rules, timeout, missing binary |
| `policy` | Golden matrix: each of the nine rules, across all three profiles, plus missing-signal cases |
| `answers` | `SystemOneResponse` → `JevAnswers` normalization, including score range |
| `client` | Each SDK exception maps to the right code |
| `credentials` | Precedence, atomic write, masking, verification failure paths |
| CLI | `key add` with mocked verification; `gate --json` and its exit codes with mocked Jev |
| Packaging | `poetry build`, wheel install, `jev-mcp --version` |

CI runs `ruff check`, `pytest`, and the wheel smoke test. **CI is required, not optional** (see acceptance criteria).

---

## 12. Documentation deliverables

README covering: pipx install, `jev-mcp key add`, Cursor `mcp.json`, tool reference, config, gate exit codes, security, and a link to [TypeSafe docs](https://docs.typesafe.ai/introduction).

---

## 13. Versioning

- `schema_version` on responses: minor bump for additive fields, major for renames.
- `questionset_id` / `policy_id` bump on material wording or rule changes; golden tests for the previous id stay in the suite.
- Package semver is independent; the changelog maps package versions to schema ids.

---

## 14. Future extensions

- `collect_lint` tool (ruff/eslint) as another state input.
- OS keychain backend for credentials.
- Nx project parameter on `run_tests`.

---

## 15. Acceptance criteria

1. `pipx install` / `poetry install` produces a working `jev-mcp` CLI.
2. `jev-mcp key add` verifies and stores the key; `key status` and `key remove` work; env overrides file; the suite never touches the real home.
3. `serve` exposes `collect_git`, `run_tests`, `decide`, `health`, `describe` per this spec.
4. `jev-mcp gate` runs the pipeline headless, emits the `decide` envelope with `--json`, and exits 0/1/2/3 per §3.2.
5. Policy golden matrix passes; CI green on ruff + pytest + wheel smoke.
6. README gets a new developer to a working Cursor connection in under 10 minutes.

---

## 16. Resolved decisions

| Topic | Decision |
|-------|----------|
| ai-router reuse | Packaging and MCP shell only |
| Tool split | `collect_git`, `run_tests`, `decide`, `health`, `describe` |
| Scope | Full production scope from the first ship |
| Key CLI | `jev-mcp key add`, verified before persisting; no MCP key tool |
| Compose | Stateless; caller passes git/tests payloads to `decide` |
| Who decides | Python policy; `next_action` is a logged cross-check |
| Retries | Owned by `typesafe_sdk.RetryPolicy` |
| Diff truncation | Per file, whole files omitted, never mid-hunk |

---

## Appendix A — Cursor MCP config

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

Use an absolute path to `jev-mcp` when the GUI PATH differs from the terminal.

## Appendix B — `gate --json` output

```json
{
  "schema_version": "1.0",
  "request_id": "2f1c…",
  "duration_ms": 1840,
  "errors": [],
  "action": "ask",
  "confidence": 0.44,
  "reasons": ["goal_ambiguous=0.72 >= 0.6"],
  "policy_trace": ["rule:goal_ambiguous", "route:ask"],
  "missing_signals": ["tests"],
  "jev": {
    "model": "jev-1.13",
    "questionset_id": "engineering-gate-v2",
    "policy_id": "policy-engineering-gate-v2",
    "answers": {}
  }
}
```
