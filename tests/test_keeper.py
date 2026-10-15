"""The mirror keeper: while PaperDaemon runs with a login it pulls at the start, on each of the tablet's change notices
and on every reconnect, and tries a failed pull again by itself."""
import threading
import time

from paperdaemon import keeper, server
from paperdaemon.remarkable import sync


class FakeNotifier:
    made = []

    def __init__(self, on_change=None):
        self.on_change, self.alive = on_change, True
        FakeNotifier.made.append(self)

    def start(self):
        return self

    def stop(self):
        self.alive = False


def until(cond, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_the_keeper_pulls_at_start_on_notices_on_reconnect_and_after_a_failure(monkeypatch):
    pulls, fail = [], {"next": False}

    def run_pull():
        pulls.append(time.time())
        if fail["next"]:
            fail["next"] = False
            server._pull["error"] = "ConnectionError: the network dropped"
            return False
        server._pull["error"] = None
        return True
    FakeNotifier.made = []
    monkeypatch.setattr(sync, "Notifier", FakeNotifier)
    monkeypatch.setattr(server, "run_pull", run_pull)
    monkeypatch.setattr(keeper, "_logged_in", lambda: True)
    monkeypatch.setattr(keeper, "RETRY_FIRST", 1)
    threading.Thread(target=keeper._keep, daemon=True).start()

    assert until(lambda: len(pulls) >= 1)                        # the first look, at the start
    time.sleep(1.5)
    n = len(pulls)
    assert n <= 2                                                # no clock while the connection is up
    FakeNotifier.made[0].on_change("the tablet")                 # the tablet synced
    assert until(lambda: len(pulls) == n + 1)
    note = FakeNotifier.made[0]
    note.alive = False                                           # the connection drops ...
    time.sleep(1.2)
    note.alive = True                                            # ... and comes back: catch up
    assert until(lambda: len(pulls) >= n + 2)
    n = len(pulls)
    fail["next"] = True
    note.on_change("the tablet")                                 # this pull fails
    assert until(lambda: len(pulls) >= n + 2, seconds=6)         # and is tried again, with no new notice
    assert len(FakeNotifier.made) == 1                           # one connection all along


def _silent_and_answering(monkeypatch, answer):
    import socket
    ours, theirs = socket.socketpair()
    monkeypatch.setattr(sync.Notifier, "_connect", lambda self: ours)
    monkeypatch.setattr(sync, "PING_AFTER", 0.3)
    monkeypatch.setattr(sync, "PONG_WAIT", 0.6)
    stop = threading.Event()

    def server():                                    # reads our pings; answers each with a pong, or never
        theirs.settimeout(0.2)
        while not stop.is_set():
            try:
                data = theirs.recv(64)
            except OSError:
                continue
            if data and answer:
                theirs.sendall(bytes([0x8A, 0x02]) + b"pd")
    threading.Thread(target=server, daemon=True).start()
    return ours, theirs, stop


def test_a_connection_the_network_dropped_is_known_dead_in_seconds(monkeypatch):
    ours, theirs, stop = _silent_and_answering(monkeypatch, answer=False)
    n = sync.Notifier().start()
    assert until(lambda: n.alive, 3)
    assert until(lambda: not n.alive, 8)                          # not 30 minutes
    assert "network" in (n.last_error or "")
    n.stop(); stop.set()


def test_a_connection_that_answers_its_pings_stays_up(monkeypatch):
    ours, theirs, stop = _silent_and_answering(monkeypatch, answer=True)
    n = sync.Notifier().start()
    assert until(lambda: n.alive, 3)
    time.sleep(6)                                                 # several pings, each answered
    assert n.alive
    n.stop(); stop.set()
