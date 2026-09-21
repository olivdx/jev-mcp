import os
import sys

import pytest

from jev_mcp.credentials import mask, remove_api_key, resolve_api_key, save_api_key, verify_api_key
from jev_mcp.errors import ApiUnreachableError, InvalidKeyError


def test_no_key_reports_none(isolated_home):
    key, source = resolve_api_key()
    assert key is None
    assert source == "none"


def test_file_key_is_found(isolated_home):
    save_api_key("file-key")
    key, source = resolve_api_key()
    assert key == "file-key"
    assert source == "file"


def test_env_overrides_file(isolated_home, monkeypatch):
    save_api_key("file-key")
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    key, source = resolve_api_key()
    assert key == "env-key"
    assert source == "env"


def test_save_uses_the_given_path(tmp_path):
    target = tmp_path / "creds.yaml"
    save_api_key("abc", path=target)
    key, source = resolve_api_key(path=target)
    assert (key, source) == ("abc", "file")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file mode")
def test_file_is_owner_only(isolated_home):
    path = save_api_key("abc")
    assert oct(os.stat(path).st_mode)[-3:] == "600"


def test_save_leaves_no_temp_file_behind(isolated_home):
    path = save_api_key("abc")
    assert list(path.parent.glob("*.tmp")) == []


def test_remove_reports_whether_a_file_was_deleted(isolated_home):
    assert remove_api_key() is False
    save_api_key("abc")
    assert remove_api_key() is True
    assert resolve_api_key()[0] is None


def test_mask_shows_only_the_tail():
    assert mask("typesafe-key-a1b2") == "…a1b2"


def test_verify_rejects_an_empty_key():
    with pytest.raises(InvalidKeyError):
        verify_api_key("   ")


def _client_raising(error: Exception):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def models(self):
            raise error

    return FakeClient


def test_verify_maps_authentication_failure(monkeypatch):
    import typesafe_sdk

    error = typesafe_sdk.TypeSafeAuthenticationError(401, None, {}, None)
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", _client_raising(error))
    with pytest.raises(InvalidKeyError):
        verify_api_key("bad-key")


def test_verify_maps_connection_failure(monkeypatch):
    import typesafe_sdk

    error = typesafe_sdk.TypeSafeAPIConnectionError("offline")
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", _client_raising(error))
    with pytest.raises(ApiUnreachableError):
        verify_api_key("some-key")


def test_verify_accepts_a_working_key(monkeypatch):
    import typesafe_sdk

    class WorkingModels:
        def list(self):
            return {"models": []}

    class WorkingClient:
        def __init__(self, **kwargs):
            WorkingClient.seen = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def models(self):
            return WorkingModels()

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", WorkingClient)
    verify_api_key("  good-key  ")
    assert WorkingClient.seen["api_key"] == "good-key"
