"""The engine's pieces around the pipeline: the text proxy, the picture requests, the loop's children and
environment, the start-script templates and the hidden --run-pipeline entry."""
import http.server
import json
import os
import socket
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from paperdaemon import __main__ as entry
from paperdaemon import card, loop, scripts, server, settings


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeChat:
    """An OpenAI-compatible server that streams two chunks and records what it was sent."""

    def __init__(self):
        seen = self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                body = b'{"status": "ok"}' if self.path == "/health" else b'{"data": [{"id": "fake"}]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.path, json.loads(self.rfile.read(n))))
                chunks = [b'data: {"choices": [{"delta": {"content": "Pho"}}]}\n\n',
                          b'data: {"choices": [{"delta": {"content": "bos"}}]}\n\n', b"data: [DONE]\n\n"]
                body = b"".join(chunks)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.port = free_port()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def fake():
    f = FakeChat()
    s = settings.load()
    settings.active(s)["text"].update(location="http://127.0.0.1:%d" % f.port, script="")
    settings.save(s)
    yield f
    f.close()


def client():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.host_token()
    return c


def test_the_proxy_streams_a_call_and_counts_it_in_flight(fake):
    c = client()
    assert c.get("/host/llm/%s/health" % server.host_token()).json()["status"] == "ok"
    r = c.post("/host/llm/%s/v1/chat/completions" % server.host_token(), json={"model": "PaperDaemon", "stream": True,
                                                      "messages": [{"role": "user", "content": "moons?"}]})
    assert r.status_code == 200 and "Pho" in r.text and "[DONE]" in r.text
    path, body = fake.seen[-1]
    assert path == "/v1/chat/completions"
    # thinking is the server's own setting: no harness adds it to the request
    assert "chat_template_kwargs" not in body
    assert card.in_flight() == {"text": 0, "image": 0} and card.idle()


def test_the_proxy_says_when_the_text_server_is_down():
    s = settings.load()
    settings.active(s)["text"].update(location="http://127.0.0.1:%d" % free_port(), script="")
    settings.save(s)
    r = client().post("/host/llm/%s/v1/chat/completions" % server.host_token(), json={"messages": []})
    assert r.status_code == 502 and card.idle()


def test_a_reference_edit_sends_the_picture_as_extra_images():
    caps = {"steps": 4, "cfg": 1.0, "sampler": "euler"}
    route, body = card.edit_body({"prompt": "make it night", "mode": "ref", "seed": 5}, caps, "QUJD", (1000, 700))
    assert route == "txt2img" and body["extra_images"] == ["QUJD"] and "ref_images" not in body
    assert (body["width"], body["height"]) == (992, 688)
    route, body = card.edit_body({"prompt": "x", "mode": "img2img", "strength": 0.3}, caps, "QUJD", (512, 512))
    assert route == "img2img" and body["init_images"] == ["QUJD"] and body["denoising_strength"] == 0.3
    with pytest.raises(ValueError, match="needs a mask"):
        card.edit_body({"prompt": "x", "mode": "inpaint"}, caps, "QUJD", (512, 512))
    with pytest.raises(ValueError, match="no edit mode"):
        card.edit_body({"prompt": "x", "mode": "warp"}, caps, "QUJD", (512, 512))


def test_a_failed_load_is_cleared_by_the_next_request():
    card._state["image"].update(phase="error", msg="the image start script ended")
    assert card.status()["states"]["image"]["phase"] == "error"
    st = card.load("image")
    assert st["phase"] == "ready" and st["key"] == "image"


def test_children_run_as_modules_and_through_the_app_in_a_packaged_build(monkeypatch):
    assert loop.pipeline_command("paperdaemon.pipeline.host") == [sys.executable, "-m", "paperdaemon.pipeline.host"]
    monkeypatch.setattr(loop, "FROZEN", True)
    cmd = loop.pipeline_command("paperdaemon.pipeline.daemon", "--once")
    assert cmd == [sys.executable, "--run-pipeline", "paperdaemon.pipeline.daemon", "--once"]


def test_the_halves_are_the_daemon_and_the_host():
    import importlib.util
    assert dict(loop.HALVES) == {"daemon": "paperdaemon.pipeline.daemon", "host": "paperdaemon.pipeline.host"}
    for _who, module in loop.HALVES:
        assert importlib.util.find_spec(module) is not None


def test_the_children_are_told_the_harness_and_the_engine():
    s = settings.load()
    env = loop.environment(s, port=8770, token="tok")
    assert env["RM_LLM"] == "http://127.0.0.1:8770/host/llm/tok"
    assert env["RM_STUDIO"] == "http://127.0.0.1:8770/host" and env["RM_STUDIO_TOKEN"] == "tok"
    assert "RM_LLM_CTX" not in env and "RM_HARNESS" not in env       # the run file carries what they did
    assert "RM_HOST_TURNS" not in env              # no hidden turn cap: tokens and repetition bound a job
    with open(env["RM_RUN"], encoding="utf-8") as f:
        har = json.load(f)
    assert har["id"] == "qwen3.8-27b" and "context" not in har["capabilities"] and "brief_additions" in har
    # what the image harness offers, for the brief: its workflows and abilities
    assert har["image"]["name"] == "stable-diffusion.cpp - FLUX.2 Klein 9B" and "edit_reference" in har["image"]["abilities"]
    assert har["image"]["workflows"]["childrensColoringBook"]["about"]
    assert har["features"]["chart"]["state"] == "on" and "output_folder" not in har["settings"]
    assert har["settings"]["prefs"] == {"temperature": "", "clock": "", "week_start": "", "language": "en"}   # nothing chosen
    s["lineup"] = "Qwen 3.6 + Klein"
    with open(loop.environment(s)["RM_RUN"], encoding="utf-8") as f:
        assert json.load(f)["text_location"] == "http://127.0.0.1:%d" % settings.TEXT_PORT


def test_a_change_of_image_model_restarts_the_host():
    s = settings.load()
    key = loop._env_key(s)
    settings.active(s)["image"]["harness"] = "z-image-turbo"
    assert loop._env_key(s) != key
    settings.active(s)["image"]["location"] = ""                 # no image slot: nothing to offer
    assert loop.harness_values(s)["image"] is None


def test_the_benchmark_environment_is_isolated(tmp_path):
    from paperdaemon import benchmark
    s = settings.load()
    env = benchmark.environment(s, 8770, "tok", str(tmp_path), str(tmp_path / "mirror"), "PaperDaemon")
    assert env["RM_STATE"] == str(tmp_path) and env["RM_MIRROR"] == env["RM_CACHE"] == str(tmp_path / "mirror")
    assert env["RM_HOST_DRY_DOCS"] == "1" and env["PYTHON_KEYRING_BACKEND"] == "keyring.backends.null.Keyring"
    assert json.loads(env["RM_TRIGGERS"]) == ["PaperDaemon"]
    run = json.load(open(env["RM_RUN"], encoding="utf-8"))
    assert run["tag_lineup"] == {"paperdaemon": settings.active(s)["name"]}


def test_nothing_is_prefilled_for_a_new_user():
    assert os.listdir(scripts.folder()) == []      # no start scripts; the blank lineup: test_settings


def test_an_inline_script_is_written_where_it_runs():
    p = scripts.runnable("text", {"script": "", "script_text": "echo hi"})
    assert os.path.isfile(p) and os.path.basename(os.path.dirname(p)) == "launch"
    assert scripts.runnable("text", {"script": "", "script_text": ""}) is None
    with pytest.raises(FileNotFoundError):
        scripts.runnable("text", {"script": "missing.bat"})


def test_run_pipeline_runs_a_module_as_main(tmp_path, monkeypatch):
    (tmp_path / "pd_hello_module.py").write_text(
        "import sys\nopen(sys.argv[1], 'w').write(__name__ + ' ' + ' '.join(sys.argv[2:]))\nraise SystemExit(4)\n",
        encoding="utf-8")
    out = tmp_path / "out.txt"
    monkeypatch.syspath_prepend(str(tmp_path))
    saved = list(sys.argv)
    try:
        assert entry.main(["--run-pipeline", "pd_hello_module", str(out), "a", "b"]) == 4
    finally:
        sys.argv = saved
    assert out.read_text() == "__main__ a b"


def test_the_host_starts_before_the_daemon(monkeypatch, tmp_path):
    order = []

    class Alive:
        def poll(self):
            return None

    def fake_spawn(who, script, env, logs=None, cwd=None):
        order.append(who)
        if who == "host":                              # the host stamps its start when it is up
            os.makedirs(tmp_path / "rm-queue", exist_ok=True)
            (tmp_path / "rm-queue" / "host-started").write_text("now")
        return Alive()
    monkeypatch.setattr(loop, "spawn", fake_spawn)
    procs = loop.spawn_halves({}, state=str(tmp_path))
    assert order == ["host", "daemon"] and set(procs) == {"host", "daemon"}
