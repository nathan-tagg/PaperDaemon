"""Pause stops the host and leaves the daemon queuing; Start brings the host back."""
from paperdaemon import loop as LP


class _Proc:
    n = 0

    def __init__(self, who):
        _Proc.n += 1
        self.who, self.pid, self.alive = who, _Proc.n, True

    def poll(self):
        return None if self.alive else 0


def test_pause_stops_the_host_only_and_start_brings_it_back(monkeypatch):
    monkeypatch.setattr(LP, "check", lambda s=None: None)
    monkeypatch.setattr(LP, "environment", lambda *a, **k: {})
    monkeypatch.setattr(LP, "_env_key", lambda s: "k")
    monkeypatch.setattr(LP, "spawn_halves", lambda env: {"host": _Proc("host"), "daemon": _Proc("daemon")})
    monkeypatch.setattr(LP, "spawn", lambda who, module, env, logs=None, cwd=None: _Proc(who))
    monkeypatch.setattr(LP, "end", lambda p: setattr(p, "alive", False) if p is not None else None)
    monkeypatch.setattr(LP, "busy", lambda state=None: None)
    monkeypatch.setattr(LP.card, "status", lambda s=None: {})
    monkeypatch.setattr(LP, "tail", lambda who, logs=None: [])
    monkeypatch.setattr(LP.S, "load", lambda: {})
    monkeypatch.setattr(LP.S, "in_use", lambda: None)
    monkeypatch.setattr(LP, "_run", dict(LP._run, thread=object()))
    monkeypatch.setattr(LP, "_procs", {})
    LP.start(8770, "t", s={})
    daemon = LP._procs["daemon"]["proc"]
    st = LP.pause()
    assert st["paused"] and not st["running"]
    assert not LP._procs["host"]["proc"].alive and daemon.alive            # the daemon goes on queuing
    st = LP.start(8770, "t", s={})
    assert st["running"] and not st["paused"]
    assert LP._procs["host"]["proc"].alive and LP._procs["daemon"]["proc"] is daemon   # the same daemon, never restarted
    LP.stop()
