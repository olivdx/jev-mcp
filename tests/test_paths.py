import pytest

from jev_mcp.errors import PathInvalidError
from jev_mcp.util.paths import config_path, credentials_path, jev_home, resolve_project_root


def test_home_follows_the_env_override(isolated_home):
    assert jev_home() == isolated_home
    assert config_path() == isolated_home / "config.yaml"
    assert credentials_path() == isolated_home / "credentials.yaml"


def test_resolve_project_root_returns_resolved_directory(tmp_path):
    assert resolve_project_root(str(tmp_path)) == tmp_path.resolve()


@pytest.mark.parametrize("raw", ["", "   "])
def test_resolve_project_root_rejects_blank(raw):
    with pytest.raises(PathInvalidError) as exc:
        resolve_project_root(raw)
    assert exc.value.code == "PATH_INVALID"


def test_resolve_project_root_rejects_missing_directory(tmp_path):
    with pytest.raises(PathInvalidError):
        resolve_project_root(str(tmp_path / "nope"))


def test_resolve_project_root_rejects_a_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(PathInvalidError):
        resolve_project_root(str(target))
