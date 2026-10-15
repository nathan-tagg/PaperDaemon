"""What the uninstaller's `--uninstall-cleanup` removes: every credential entry PaperDaemon keeps (by its exact name)
and its data folder -- and nothing else: another program's credentials and the folder next to PaperDaemon's stay.
The program folder, the shortcuts, the Start menu entry and the window's cache are removed by the uninstaller itself
(shell/installer/installer.nsi)."""
import keyring
import keyring.backend

from paperdaemon import __main__ as M
from paperdaemon import vault


class Memory(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        self.store.pop((service, name))


def test_cleanup_removes_paperdaemons_credentials_and_data_and_nothing_else(tmp_path, monkeypatch):
    mem = Memory()
    monkeypatch.setattr(keyring, "get_keyring", lambda: mem)
    monkeypatch.setattr(keyring, "get_password", mem.get_password)
    monkeypatch.setattr(keyring, "set_password", mem.set_password)
    monkeypatch.setattr(keyring, "delete_password", mem.delete_password)
    for name in vault.NAMES:
        mem.set_password(vault.SERVICE, name, "secret-" + name)
    mem.set_password("SomeOtherApp", "token", "keep me")
    data = tmp_path / "PaperDaemon"
    (data / "mirror").mkdir(parents=True)
    (data / "mirror" / "doc.content").write_text("{}")
    (data / "settings.json").write_text("{}")
    neighbor = tmp_path / "SomeOtherApp"
    neighbor.mkdir()
    (neighbor / "keep.txt").write_text("keep")
    monkeypatch.setenv("PAPERDAEMON_HOME", str(data))
    assert M.uninstall_cleanup() == 0
    assert not data.exists()
    assert (neighbor / "keep.txt").read_text() == "keep"
    assert all(mem.get_password(vault.SERVICE, n) is None for n in vault.NAMES)
    assert mem.get_password("SomeOtherApp", "token") == "keep me"


def test_cleanup_removes_the_api_keys_by_their_index(monkeypatch, tmp_path):
    mem = Memory()
    for f in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, f, getattr(mem, f))
    monkeypatch.setattr(keyring, "get_keyring", lambda: mem)
    name = vault.key_name("text", "api.example.com")
    vault.put(name, "sk-test")
    assert mem.get_password(vault.SERVICE, name) == "sk-test"
    monkeypatch.setenv("PAPERDAEMON_HOME", str(tmp_path / "PaperDaemon"))
    assert M.uninstall_cleanup() == 0
    assert mem.store == {}                                   # the key, and the index that named it


def test_cleanup_never_deletes_a_home_or_a_drive(monkeypatch, tmp_path):
    monkeypatch.setattr(vault, "forget_all", lambda: [])
    home = tmp_path / "user"
    (home / "Documents").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    for data in (home, tmp_path):                            # the home itself, and a folder above it
        monkeypatch.setenv("PAPERDAEMON_HOME", str(data))
        assert M.uninstall_cleanup() == 1
        assert (home / "Documents").is_dir()


def test_the_windowless_cleanup_leaves_no_log_behind(monkeypatch, tmp_path):
    # the installed engine has no console: its streams are None, and the error log they would open lives in the
    # very folder being deleted
    import sys
    monkeypatch.setattr(vault, "forget_all", lambda: [])
    data = tmp_path / "PaperDaemon"
    (data / "mirror").mkdir(parents=True)
    monkeypatch.setenv("PAPERDAEMON_HOME", str(data))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert M.main(["--uninstall-cleanup"]) == 0
    assert not data.exists()
