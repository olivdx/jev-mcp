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
            TestProjectRule(
                match=str(rule["match"]),
                command=[str(part) for part in rule["command"]],
            )
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
