import textwrap

from jev_mcp.config import AppConfig, load_config


def test_defaults_are_complete():
    cfg = load_config(use_user_file=False)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8089
    assert cfg.tests.default_timeout_s == 600
    assert cfg.jev.model == "jev-latest"
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
