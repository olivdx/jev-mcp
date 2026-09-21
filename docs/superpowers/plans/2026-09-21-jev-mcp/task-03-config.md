# Task 3 — Configuration

**Deliverable:** `load_config()` returning a fully typed `AppConfig` built from defaults, then YAML, then environment variables.

**Files:**
- Create: `src/jev_mcp/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `jev_mcp.util.paths.config_path` (task 2).
- Produces: `AppConfig`, `GitConfig`, `TestsConfig`, `TestProjectRule`, `JevConfig`, `DecisionConfig`, `Thresholds`, `load_config`.

**Precedence:** defaults → YAML file → environment. Environment always wins.

---

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import textwrap

from jev_mcp.config import AppConfig, load_config


def test_defaults_are_complete():
    cfg = load_config(use_user_file=False)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8089
    assert cfg.git.max_diff_bytes == 524_288
    assert cfg.git.max_file_diff_bytes == 65_536
    assert cfg.tests.default_timeout_s == 600
    assert cfg.jev.model == "jev-1.13"
    assert cfg.jev.max_retries == 2
    assert cfg.decision.default_profile == "default"
    assert cfg.decision.thresholds.tests_blocking_fix == 0.6


def test_yaml_overrides_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        textwrap.dedent(
            """
            port: 9000
            log_format: json
            git:
              max_diff_bytes: 1024
            tests:
              default_timeout_s: 30
              projects:
                - match: "pyproject.toml"
                  command: ["pytest", "-q"]
            jev:
              model: jev-9.9
            decision:
              thresholds:
                tests_blocking_fix: 0.8
            """
        ),
        encoding="utf-8",
    )
    cfg = load_config(config_file)
    assert cfg.port == 9000
    assert cfg.log_format == "json"
    assert cfg.git.max_diff_bytes == 1024
    assert cfg.git.max_file_diff_bytes == 65_536  # untouched key keeps its default
    assert cfg.tests.default_timeout_s == 30
    assert cfg.tests.projects[0].match == "pyproject.toml"
    assert cfg.tests.projects[0].command == ["pytest", "-q"]
    assert cfg.jev.model == "jev-9.9"
    assert cfg.decision.thresholds.tests_blocking_fix == 0.8
    assert cfg.decision.thresholds.goal_ambiguous_ask == 0.6


def test_env_beats_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("port: 9000\njev:\n  model: jev-from-yaml\n", encoding="utf-8")
    monkeypatch.setenv("JEV_MCP_PORT", "9999")
    monkeypatch.setenv("JEV_MCP_JEV_MODEL", "jev-from-env")
    cfg = load_config(config_file)
    assert cfg.port == 9999
    assert cfg.jev.model == "jev-from-env"


def test_missing_file_is_not_an_error(tmp_path):
    cfg = load_config(tmp_path / "absent.yaml")
    assert isinstance(cfg, AppConfig)
    assert cfg.port == 8089


def test_log_redact_env_accepts_false(monkeypatch):
    monkeypatch.setenv("JEV_MCP_LOG_REDACT", "false")
    assert load_config(use_user_file=False).log_redact is False
```

- [ ] **Step 2: Run and confirm failure**

Run: `poetry run pytest tests/test_config.py -v`

Expected: `ModuleNotFoundError: No module named 'jev_mcp.config'`.

- [ ] **Step 3: Implement `config.py`**

```python
# src/jev_mcp/config.py
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from jev_mcp.util.paths import config_path


@dataclass(frozen=True)
class GitConfig:
    max_diff_bytes: int = 524_288
    max_file_diff_bytes: int = 65_536
    max_stat_files: int = 500


@dataclass(frozen=True)
class TestProjectRule:
    match: str
    command: list[str]


@dataclass(frozen=True)
class TestsConfig:
    default_timeout_s: int = 600
    max_output_bytes: int = 262_144
    env_allowlist: list[str] = field(default_factory=lambda: ["CI", "PATH", "HOME", "LANG"])
    projects: list[TestProjectRule] = field(default_factory=list)


@dataclass(frozen=True)
class JevConfig:
    model: str = "jev-1.13"
    request_timeout_s: float = 60.0
    max_retries: int = 2


@dataclass(frozen=True)
class Thresholds:
    goal_ambiguous_ask: float = 0.6
    tests_blocking_fix: float = 0.6
    goal_addressed_min: float = 0.5
    incomplete_work_fix: float = 0.6
    scope_creep_ask: float = 0.7
    risk_high_normalized: float = 0.67
    crosscheck_min_confidence: float = 0.5


@dataclass(frozen=True)
class DecisionConfig:
    default_profile: str = "default"
    thresholds: Thresholds = field(default_factory=Thresholds)


@dataclass(frozen=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8089
    log_level: str = "info"
    log_format: str = "text"
    log_redact: bool = True
    git: GitConfig = field(default_factory=GitConfig)
    tests: TestsConfig = field(default_factory=TestsConfig)
    jev: JevConfig = field(default_factory=JevConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)


def load_config(path: Path | None = None, *, use_user_file: bool = True) -> AppConfig:
    cfg = AppConfig()
    source = path if path is not None else (config_path() if use_user_file else None)
    if source is not None and source.exists():
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            cfg = _merge_yaml(cfg, raw)
    return _apply_env(cfg)


def _merge_yaml(cfg: AppConfig, raw: dict) -> AppConfig:
    git = cfg.git
    if isinstance(raw.get("git"), dict):
        section = raw["git"]
        git = GitConfig(
            max_diff_bytes=int(section.get("max_diff_bytes", git.max_diff_bytes)),
            max_file_diff_bytes=int(section.get("max_file_diff_bytes", git.max_file_diff_bytes)),
            max_stat_files=int(section.get("max_stat_files", git.max_stat_files)),
        )

    tests = cfg.tests
    if isinstance(raw.get("tests"), dict):
        section = raw["tests"]
        rules = [
            TestProjectRule(match=str(rule["match"]), command=[str(part) for part in rule["command"]])
            for rule in section.get("projects", [])
            if isinstance(rule, dict) and rule.get("match") and rule.get("command")
        ]
        tests = TestsConfig(
            default_timeout_s=int(section.get("default_timeout_s", tests.default_timeout_s)),
            max_output_bytes=int(section.get("max_output_bytes", tests.max_output_bytes)),
            env_allowlist=[str(v) for v in section.get("env_allowlist", tests.env_allowlist)],
            projects=rules or tests.projects,
        )

    jev = cfg.jev
    if isinstance(raw.get("jev"), dict):
        section = raw["jev"]
        jev = JevConfig(
            model=str(section.get("model", jev.model)),
            request_timeout_s=float(section.get("request_timeout_s", jev.request_timeout_s)),
            max_retries=int(section.get("max_retries", jev.max_retries)),
        )

    decision = cfg.decision
    if isinstance(raw.get("decision"), dict):
        section = raw["decision"]
        thresholds = decision.thresholds
        if isinstance(section.get("thresholds"), dict):
            values = section["thresholds"]
            thresholds = Thresholds(
                **{
                    name: float(values.get(name, getattr(thresholds, name)))
                    for name in Thresholds.__dataclass_fields__
                }
            )
        decision = DecisionConfig(
            default_profile=str(section.get("default_profile", decision.default_profile)),
            thresholds=thresholds,
        )

    return replace(
        cfg,
        host=str(raw.get("host", cfg.host)),
        port=int(raw.get("port", cfg.port)),
        log_level=str(raw.get("log_level", cfg.log_level)),
        log_format=str(raw.get("log_format", cfg.log_format)),
        log_redact=bool(raw.get("log_redact", cfg.log_redact)),
        git=git,
        tests=tests,
        jev=jev,
        decision=decision,
    )


def _as_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _apply_env(cfg: AppConfig) -> AppConfig:
    if value := os.getenv("JEV_MCP_HOST"):
        cfg = replace(cfg, host=value)
    if value := os.getenv("JEV_MCP_PORT"):
        cfg = replace(cfg, port=int(value))
    if value := os.getenv("JEV_MCP_LOG_LEVEL"):
        cfg = replace(cfg, log_level=value)
    if value := os.getenv("JEV_MCP_LOG_FORMAT"):
        cfg = replace(cfg, log_format=value)
    if value := os.getenv("JEV_MCP_LOG_REDACT"):
        cfg = replace(cfg, log_redact=_as_bool(value))
    if value := os.getenv("JEV_MCP_GIT_MAX_DIFF_BYTES"):
        cfg = replace(cfg, git=replace(cfg.git, max_diff_bytes=int(value)))
    if value := os.getenv("JEV_MCP_TESTS_TIMEOUT_S"):
        cfg = replace(cfg, tests=replace(cfg.tests, default_timeout_s=int(value)))
    if value := os.getenv("JEV_MCP_JEV_MODEL"):
        cfg = replace(cfg, jev=replace(cfg.jev, model=value))
    if value := os.getenv("JEV_MCP_JEV_TIMEOUT_S"):
        cfg = replace(cfg, jev=replace(cfg.jev, request_timeout_s=float(value)))
    if value := os.getenv("JEV_MCP_DEFAULT_PROFILE"):
        cfg = replace(cfg, decision=replace(cfg.decision, default_profile=value))
    return cfg
```

- [ ] **Step 4: Run the tests**

Run: `poetry run pytest tests/test_config.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/jev_mcp/config.py tests/test_config.py
git commit -m "feat: add typed configuration with yaml and env overrides"
```
