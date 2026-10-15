"""Taking the reMarkable desktop app's login, against a stand-in registry (the real one is never touched):
borrow copies it; steal copies it, then removes exactly the app's two login values, and only once the
copy is stored; steal refuses while the app runs."""
import pytest
from fastapi.testclient import TestClient

from paperdaemon import server, vault
from paperdaemon.remarkable import auth, desktop_token

KEY = r"Software\reMarkable\desktop"


class FakeRegistry:
    """The few winreg calls desktop_token makes, over a dict of {key path: {name: value}}."""
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE, KEY_QUERY_VALUE = 2, 1

    def __init__(self, keys):
        self.keys = keys

    class _Key:
        def __init__(self, values):
            self.values = values

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, *rest):
        if path not in self.keys:
            raise OSError("no such key")
        return self._Key(self.keys[path])

    def QueryValueEx(self, k, name):
        if name not in k.values:
            raise OSError("no such value")
        return k.values[name], 1

    def DeleteValue(self, k, name):
        if name not in k.values:
            raise OSError("no such value")
        del k.values[name]


@pytest.fixture
def registry(monkeypatch):
    reg = FakeRegistry({KEY: {"devicetoken": "@ByteArray(header.e30.sig)", "UserToken": "session",
                              "WindowWidth": 900, "PaperSize": b"\x00\x01", "UpdateUUID": "{x}"}})
    monkeypatch.setattr(desktop_token, "_registry", lambda: reg)
    return reg


def client():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    return c


def test_borrow_copies_the_login_and_leaves_the_app_signed_in(registry, fresh):
    r = client().post("/api/v1/tablet/desktop-token", json={"mode": "borrow"}).json()
    assert r == {"found": True, "set": True}
    assert fresh.get_password("PaperDaemon", auth.DEVICE_KEY) == "header.e30.sig"
    assert set(registry.keys[KEY]) == {"devicetoken", "UserToken", "WindowWidth", "PaperSize", "UpdateUUID"}


def test_steal_copies_then_removes_only_the_two_login_values(registry, fresh):
    r = client().post("/api/v1/tablet/desktop-token", json={"mode": "steal"}).json()
    assert r["found"] and r["set"] and sorted(r["removed"]) == ["UserToken", "devicetoken"]
    assert fresh.get_password("PaperDaemon", auth.DEVICE_KEY) == "header.e30.sig"
    assert set(registry.keys[KEY]) == {"WindowWidth", "PaperSize", "UpdateUUID"}


def test_steal_refuses_while_the_app_runs_and_changes_nothing(registry, fresh, monkeypatch):
    monkeypatch.setattr(desktop_token, "app_running", lambda: True)
    r = client().post("/api/v1/tablet/desktop-token", json={"mode": "steal"})
    assert r.status_code == 409 and "Quit the reMarkable app" in r.json()["error"]
    assert "devicetoken" in registry.keys[KEY] and not vault.has(auth.DEVICE_KEY)


def test_steal_removes_nothing_when_the_copy_could_not_be_stored(registry, fresh, monkeypatch):
    def broken(token):
        raise RuntimeError("the credential store is locked")
    monkeypatch.setattr(auth, "set_device_token", broken)
    r = client().post("/api/v1/tablet/desktop-token", json={"mode": "steal"}).json()
    assert r["set"] is False and "removed" not in r
    assert {"devicetoken", "UserToken"} <= set(registry.keys[KEY])


def test_no_login_is_reported_as_not_found(fresh, monkeypatch):
    monkeypatch.setattr(desktop_token, "_registry", lambda: FakeRegistry({}))
    assert client().post("/api/v1/tablet/desktop-token", json={"mode": "steal"}).json() == {"found": False, "set": False}
    assert client().post("/api/v1/tablet/desktop-token", json={"mode": "other"}).status_code == 400
