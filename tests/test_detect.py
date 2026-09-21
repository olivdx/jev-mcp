import json

from jev_mcp.collectors.detect import detect_test_command
from jev_mcp.config import TestProjectRule, TestsConfig

CFG = TestsConfig()


def test_no_markers_returns_none(tmp_path):
    assert detect_test_command(tmp_path, CFG) is None


def test_pyproject_maps_to_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "pytest"
    assert command == ["pytest", "-q"]


def test_poetry_lock_prefixes_poetry_run(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
    _, command = detect_test_command(tmp_path, CFG)
    assert command == ["poetry", "run", "pytest", "-q"]


def test_package_json_with_test_script(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "npm"
    assert command == ["npm", "test"]


def test_package_json_without_test_script_is_ignored(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "x"}}), encoding="utf-8")
    assert detect_test_command(tmp_path, CFG) is None


def test_malformed_package_json_does_not_crash(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert detect_test_command(tmp_path, CFG) is None


def test_makefile_test_target(tmp_path):
    (tmp_path / "Makefile").write_text("build:\n\techo b\ntest:\n\techo t\n", encoding="utf-8")
    runner_id, command = detect_test_command(tmp_path, CFG)
    assert runner_id == "make"
    assert command == ["make", "test"]


def test_config_rule_wins_over_builtin(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n", encoding="utf-8")
    cfg = TestsConfig(
        projects=[TestProjectRule(match="pyproject.toml", command=["nx", "test", "api"])]
    )
    runner_id, command = detect_test_command(tmp_path, cfg)
    assert runner_id == "config:pyproject.toml"
    assert command == ["nx", "test", "api"]


def test_first_matching_config_rule_wins(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}), encoding="utf-8")
    cfg = TestsConfig(
        projects=[
            TestProjectRule(match="absent.toml", command=["never"]),
            TestProjectRule(match="package.json", command=["pnpm", "test"]),
        ]
    )
    _, command = detect_test_command(tmp_path, cfg)
    assert command == ["pnpm", "test"]
