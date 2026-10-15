import pytest

from paperdaemon import vault
from paperdaemon.remarkable import auth, sync


def test_secrets_can_be_replaced_and_removed():
    vault.put("key:image", "first-value")
    vault.put("key:image", "second-value")
    assert vault.get("key:image") == "second-value" and vault.has("key:image")
    vault.put("key:image", "")                         # an empty paste removes it
    assert not vault.has("key:image")
    vault.delete("key:image")                          # removing twice is harmless


def test_each_server_keeps_its_own_key_and_the_uninstaller_finds_them_all():
    a, o = vault.key_name("text", "https://api.anthropic.com/v1"), vault.key_name("text", "https://openrouter.ai/api")
    assert a == "key:text:api.anthropic.com" and o == "key:text:openrouter.ai"
    vault.put(a, "one")
    vault.put(o, "two")                                # another lineup's provider: the first key stays
    assert vault.get(a) == "one" and sorted(vault.keys()) == [a, o]
    assert sorted(vault.forget_all()) == [a, o] and vault.keys() == [] and vault.get(a) is None


def test_a_pasted_desktop_app_token_is_unwrapped_and_the_session_ends():
    auth._TOKEN.update(jwt="a-session", exp=9e18)
    auth.set_device_token("  @ByteArray(abc.def.ghi)  ")
    assert vault.get(auth.DEVICE_KEY) == "abc.def.ghi"
    assert auth._TOKEN["jwt"] is None


def test_without_a_token_the_cloud_reports_not_connected():
    with pytest.raises(auth.NotConnected):
        auth.device_token()


def test_a_session_of_api_calls_writes_no_token_and_no_secret_anywhere(caplog):
    """The pairing token and a stored key appear in no log record and in no file of the data folder."""
    import logging
    import os
    from fastapi.testclient import TestClient
    from paperdaemon import paths, server
    caplog.set_level(logging.DEBUG)
    c = TestClient(server.app)
    tok = server.pairing_token()
    c.headers["Authorization"] = "Bearer " + tok
    key = "sk-never-in-a-log-0123456789"
    c.put("/api/v1/secret/text_key", json={"value": key})
    for path in ("/api/v1/status", "/api/v1/settings", "/api/v1/lineups", "/api/v1/jobs", "/api/v1/models",
                 "/api/v1/notepads", "/api/v1/nothing-here"):
        c.get(path)
    c.get("/api/v1/status", headers={"Authorization": "Bearer wrong-" + tok})
    text = caplog.text
    for root, _dirs, files in os.walk(paths.data_dir()):
        for f in files:
            try:
                text += open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
            except OSError:
                pass
    assert tok not in text and key not in text
    c.delete("/api/v1/secret/text_key")
