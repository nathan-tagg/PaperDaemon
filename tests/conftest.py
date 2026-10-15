"""Every test runs on its own data folder and an in-memory credential store: never the user's
settings, never the operating system's real store."""
import os
import tempfile

import keyring
import keyring.backend
import keyring.errors
import pytest

os.environ["PAPERDAEMON_HOME"] = tempfile.mkdtemp(prefix="paperdaemon-test-")


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("not set")
        del self.store[(service, username)]


keyring.set_keyring(MemoryKeyring())


def _test_lineup(name, text_script, text_harness, image_script, image_harness):
    from paperdaemon import settings
    text = dict(settings.slot_defaults("text"), location="http://127.0.0.1:%d" % settings.TEXT_PORT,
                script=text_script, harness=text_harness)
    image = dict(settings.slot_defaults("image"), location="http://127.0.0.1:%d" % settings.IMAGE_PORT,
                 script=image_script, harness=image_harness)
    return {"name": name, "text": text, "image": image}


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERDAEMON_HOME", str(tmp_path))
    ring = MemoryKeyring()
    keyring.set_keyring(ring)
    from paperdaemon import card, harnesses, server, settings
    from paperdaemon.remarkable import desktop_token
    # never the real registry: the reMarkable app's login on this computer must not be read or removed
    monkeypatch.setattr(desktop_token, "_registry", lambda: None)
    monkeypatch.setattr(desktop_token, "app_running", lambda: False)
    from paperdaemon.models import checks, slots
    server._pair["token"] = None
    slots._reported.update(text=[], image=[])
    checks._last.update(text=None, image=None)
    settings.force(None)
    # the tests work on two local lineups of their own; PaperDaemon itself ships one blank lineup
    # (test_settings checks that)
    test_lineups = [_test_lineup("Qwen 3.8 + Klein", "qwen3.8-27b.bat", "qwen3.8-27b", "flux2-klein-9b.bat", "flux.2-klein-9b"),
                    _test_lineup("Qwen 3.6 + Klein", "qwen3.6-27b.bat", "qwen3.6-27b", "flux2-klein-9b.bat", "flux.2-klein-9b")]
    monkeypatch.setattr(settings, "SHIPPED_LINEUPS", test_lineups)
    monkeypatch.setattr(settings, "DEFAULT_LINEUP", "Qwen 3.8 + Klein")
    monkeypatch.setitem(settings.DEFAULTS, "lineups", test_lineups)
    monkeypatch.setitem(settings.DEFAULTS, "lineup", "Qwen 3.8 + Klein")
    harnesses._user.update(key=None, made=(), errors=[])
    with card._cond:
        card._inflight.update(text=0, image=0)
        card._run.update(loading=None, wanted="text")
        for st in card._state.values():
            st.update(phase="idle", msg="", since=None)
    yield ring
