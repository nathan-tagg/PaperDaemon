"""The start-script contract and the engine rule, against dummy servers on test ports: small Python HTTP
servers that answer the health routes, never a real model."""
import http.server
import json
import os
import socket
import sys
import threading
import time

import pytest

from paperdaemon import card, settings
from paperdaemon.models import hotswap

PY = sys.executable
DUMMY = """
import http.server, json, os, sys, time
port, delay = int(sys.argv[1]), float(sys.argv[2])
if len(sys.argv) > 3:
    with open(sys.argv[3], "w") as f:
        json.dump({k: v for k, v in os.environ.items() if k.startswith("PAPERDAEMON_")}, f)
time.sleep(delay)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"data": [{"id": "dummy"}]}'
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer.allow_reuse_address = False   # a port in use fails the bind, as a real server does
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
"""
WINDOWS = sys.platform == "win32"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def wait_closed(port, limit=10):
    deadline = time.time() + limit
    while listening(port) and time.time() < deadline:
        time.sleep(0.1)
    return not listening(port)


@pytest.fixture
def dummy(tmp_path):
    path = tmp_path / "dummy_server.py"
    path.write_text(DUMMY, encoding="utf-8")
    yield str(path)
    hotswap.stop_all()


def script(dummy, port, delay=0.3, env_out=None, count=None):
    lines = []
    if count:
        lines.append('echo run>>"%s"' % count if WINDOWS else 'echo run >> "%s"' % count)
    cmd = '"%s" "%s" %d %s' % (PY, dummy, port, delay)
    if env_out:
        cmd += ' "%s"' % env_out
    lines.append(cmd)
    return "\n".join(lines)


def configure(text=None, image=None, text_port=None, image_port=None):
    s = settings.load()
    lu = settings.active(s)
    lu["text"].update(location="http://127.0.0.1:%d" % (text_port or free_port()), script="",
                      script_text=text or "")
    lu["image"].update(location="http://127.0.0.1:%d" % (image_port or free_port()), script="",
                       api="openai-images", script_text=image or "")
    return settings.save(s)


def runs(path):
    try:
        with open(path) as f:
            return len([x for x in f if x.strip()])
    except OSError:
        return 0


class Foreign:
    """A server some other program left on a port."""

    def __init__(self, port):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"data": []}')

            def log_message(self, *a):
                pass
        self.httpd = http.server.HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_start_waits_for_the_server_and_stop_ends_it(dummy):
    tp = free_port()
    s = configure(text=script(dummy, tp), text_port=tp)
    srv = hotswap.start("text", s)
    assert srv.ready and listening(tp)
    assert hotswap.status("text", s)["started_by_paperdaemon"] is True
    assert hotswap.stop("text") is True
    assert wait_closed(tp)                             # the child python died with the job


def test_a_script_that_fails_shows_its_last_lines(dummy):
    tp = free_port()
    s = configure(text='"%s" -c "import sys; print(\'model file not found\'); sys.exit(3)"' % PY, text_port=tp)
    with pytest.raises(hotswap.LaunchFailed, match="exit code 3.*model file not found"):
        hotswap.start("text", s)


def test_the_script_gets_the_contract_environment(dummy, tmp_path):
    tp, ip = free_port(), free_port()
    env_out = str(tmp_path / "env.json")
    s = configure(text=script(dummy, tp, env_out=env_out), text_port=tp, image_port=ip)
    hotswap.start("text", s)
    with open(env_out) as f:
        env = json.load(f)
    assert env["PAPERDAEMON_ROLE"] == "text"
    assert env["PAPERDAEMON_LOCATION"] == "http://127.0.0.1:%d" % tp
    assert env["PAPERDAEMON_HOST"] == "127.0.0.1" and env["PAPERDAEMON_PORT"] == str(tp)
    assert env["PAPERDAEMON_OTHER_LOCATION"] == "http://127.0.0.1:%d" % ip
    assert env["PAPERDAEMON_LINEUP"] == "Qwen 3.8 + Klein"
    assert env["PAPERDAEMON_DATA"]


def test_the_script_runs_only_when_our_server_is_not_running(dummy, tmp_path):
    tp = free_port()
    count = str(tmp_path / "count.txt")
    configure(text=script(dummy, tp, count=count), text_port=tp)
    card.ensure("text")
    card.ensure("text")
    with card.call("text"):
        pass
    assert runs(count) == 1
    hotswap.stop("text")
    assert wait_closed(tp)
    card.ensure("text")                                # ours ended: the next call runs the script again
    assert runs(count) == 2


def test_a_foreign_server_on_the_port_is_never_taken_for_ours(dummy, tmp_path):
    tp = free_port()
    count = str(tmp_path / "count.txt")
    configure(text=script(dummy, tp, delay=1.0, count=count), text_port=tp)
    foreign = Foreign(tp)
    try:
        # the script runs although something answers; its server cannot take the port and exits
        with pytest.raises(card.NotReady):
            card.ensure("text")
        assert runs(count) == 1
        assert listening(tp)                           # the other program's server is left alone
    finally:
        foreign.close()


def test_a_script_that_hands_its_server_off_runs_before_each_call(tmp_path):
    tp = free_port()
    count = str(tmp_path / "count.txt")
    text = ('echo run>>"%s"\nexit /b 0' % count) if WINDOWS else ('echo run >> "%s"\nexit 0' % count)
    configure(text=text, text_port=tp)
    foreign = Foreign(tp)                              # the service the script hands off to
    try:
        card.ensure("text")
        assert hotswap.ours("text") is None            # nothing of ours is running
        card.ensure("text")
        assert runs(count) == 2
    finally:
        foreign.close()


def test_a_script_that_exits_cleanly_with_nothing_answering_fails(tmp_path):
    tp = free_port()
    configure(text="echo nothing to start", text_port=tp)
    with pytest.raises(card.NotReady, match="exit code 0.*nothing to start"):
        card.ensure("text")


def test_no_script_runs_while_a_call_is_in_flight(dummy, tmp_path):
    tp, ip = free_port(), free_port()
    icount = str(tmp_path / "image.txt")
    configure(text=script(dummy, tp), image=script(dummy, ip, count=icount), text_port=tp, image_port=ip)
    done = threading.Event()
    with card.call("text"):
        th = threading.Thread(target=lambda: (card.ensure("image"), done.set()), daemon=True)
        th.start()
        time.sleep(1.5)
        assert runs(icount) == 0 and not done.is_set()   # the image script waits for the text call
        assert not card.idle()
    th.join(30)
    assert done.is_set() and runs(icount) == 1 and listening(ip)


def test_a_slot_without_a_script_is_used_as_it_is():
    tp = free_port()
    configure(text="", text_port=tp)
    foreign = Foreign(tp)
    try:
        assert card.ready("text")
        with card.call("text") as srv:
            assert srv is None
        assert hotswap.ours("text") is None
    finally:
        foreign.close()


def test_a_slot_without_a_location_is_not_ready():
    s = settings.load()
    settings.active(s)["image"]["location"] = ""
    settings.save(s)
    with pytest.raises(card.NotReady, match="no location"):
        card.ensure("image")


@pytest.mark.skipif(not WINDOWS, reason="the listener check reads the Windows TCP table")
def test_the_listener_check_tells_ours_from_foreign(dummy):
    tp = free_port()
    s = configure(text=script(dummy, tp), text_port=tp)
    srv = hotswap.start("text", s)
    assert srv.owns_listener("http://127.0.0.1:%d" % tp) is True
    other = free_port()
    foreign = Foreign(other)
    try:
        assert srv.owns_listener("http://127.0.0.1:%d" % other) is False
    finally:
        foreign.close()
    assert srv.owns_listener("http://10.1.2.3:%d" % tp) is None          # not this computer: cannot tell


def test_a_job_on_another_lineup_runs_its_script_only_when_it_differs(dummy, tmp_path):
    """Every lineup is live: the start script runs when the job's lineup needs a different one than the last
    loaded (the other lineup's server ends first), and not when both use the same."""
    tp, tq = free_port(), free_port()
    ca, cb = str(tmp_path / "a.txt"), str(tmp_path / "b.txt")
    s = settings.load()
    a, b = s["lineups"][0], s["lineups"][1]
    a["text"].update(location="http://127.0.0.1:%d" % tp, script="", script_text=script(dummy, tp, count=ca))
    b["text"].update(location="http://127.0.0.1:%d" % tq, script="", script_text=script(dummy, tq, count=cb))
    settings.save(s)
    try:
        settings.use(a["name"])
        card.ensure("text")
        settings.use(b["name"])
        card.ensure("text")                            # another script: lineup A's server ends, B's starts
        assert runs(ca) == 1 and runs(cb) == 1 and wait_closed(tp)
        card.ensure("text")                            # the last loaded is the one needed: nothing runs
        assert runs(cb) == 1
        s = settings.load()
        s["lineups"][0]["text"] = dict(s["lineups"][1]["text"])     # A now uses B's very script and server
        settings.save(s)
        settings.use(s["lineups"][0]["name"])
        card.ensure("text")
        assert runs(cb) == 1
    finally:
        settings.use(None)
