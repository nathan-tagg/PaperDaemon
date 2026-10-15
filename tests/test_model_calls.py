"""The host's model calls: one door (the engine), any API family, and no clock on a call.

- An OpenAI-format request becomes an adapter's neutral call and its reply an OpenAI-format stream, so an
  Anthropic text slot runs jobs through the same host code.
- A reply that loops is stopped by the runaway guard (repetition), whatever the time.
- A server that stalls is waited for: the call ends when the server's process ends, never on a timer.
"""
import base64
import json
import os
import subprocess
import sys
import textwrap
import time

from fastapi.testclient import TestClient

from paperdaemon import server, settings
from paperdaemon.models import adapters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_a_host_request_becomes_a_neutral_call_and_the_reply_a_stream():
    png = base64.b64encode(b"\x89PNG").decode()
    req = adapters.from_openai({
        "messages": [{"role": "system", "content": "the brief"},
                     {"role": "user", "content": [{"type": "text", "text": "the page"},
                                                  {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png}}]},
                     {"role": "assistant", "content": None, "tool_calls": [
                         {"id": "c1", "type": "function", "function": {"name": "plan", "arguments": "{\"steps\": []}"}}]},
                     {"role": "tool", "tool_call_id": "c1", "name": "plan", "content": "planned"}],
        "tools": [{"type": "function", "function": {"name": "plan", "description": "d", "parameters": {"type": "object"}}}],
        "tool_choice": "required", "max_tokens": 99})
    assert req["system"] == "the brief" and req["force_tool"] and req["max_tokens"] == 99
    assert req["messages"][0] == {"role": "user", "text": "the page", "images": [b"\x89PNG"]}
    assert req["messages"][1]["tool_calls"] == [{"id": "c1", "name": "plan", "arguments": {"steps": []}}]
    assert req["messages"][2]["role"] == "tool" and req["tools"][0]["name"] == "plan"
    sse = adapters.openai_stream({"text": "", "tool_calls": [{"id": "t", "name": "skip", "arguments": {"note": "n"}}],
                                  "stop": "tool_use", "usage": {"input": 5, "output": 2}}).decode()
    events = [json.loads(l[5:]) for l in sse.splitlines() if l.startswith("data:") and "[DONE]" not in l]
    call = events[0]["choices"][0]["delta"]["tool_calls"][0]
    assert call["function"]["name"] == "skip" and json.loads(call["function"]["arguments"]) == {"note": "n"}
    assert events[0]["choices"][0]["finish_reason"] == "tool_calls" and sse.rstrip().endswith("[DONE]")


def test_an_anthropic_text_slot_answers_the_host_through_the_engine(monkeypatch, fresh):
    s = settings.load()
    s["lineups"][0]["text"].update(location="https://api.example.com", api="anthropic", script="")
    settings.save(s)
    seen = {}

    class Fake:
        def chat(self, **kw):
            seen.update(kw)
            return {"text": "", "tool_calls": [{"id": "x", "name": "skip", "arguments": {"note": "nothing asked"}}],
                    "stop": "tool_use", "usage": {"input": 1, "output": 1}}
    monkeypatch.setattr(adapters, "for_slot", lambda role, s=None, m=None: Fake())
    monkeypatch.setattr(server.card, "acquire", lambda role, *a, **k: None)
    monkeypatch.setattr(server.card, "release", lambda role, *a, **k: None)
    c = TestClient(server.app)
    r = c.post("/host/llm/%s/v1/chat/completions" % server.host_token(),
               json={"messages": [{"role": "user", "content": "hi"}], "stream": True,
                     "tools": [{"type": "function", "function": {"name": "skip", "parameters": {"type": "object"}}}],
                     "tool_choice": "required"})
    assert r.status_code == 200 and "skip" in r.text and "[DONE]" in r.text
    assert seen["force_tool"] and seen["messages"][0]["text"] == "hi"


STUB = textwrap.dedent('''
    import http.server, sys, time, json
    MODE = sys.argv[2]
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status": "ok"}')
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.flush()
            if MODE == "stall":
                time.sleep(3600)
            chunk = {"choices": [{"index": 0, "delta": {"content": "the same forty characters, over and over "}}]}
            while True:
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\\n\\n")
                self.wfile.flush()
    http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
''')

CALL = textwrap.dedent('''
    import json, sys, time
    sys.path.insert(0, %(root)r)
    from paperdaemon.pipeline import host as H
    t = time.time()
    try:
        text, finish = H.plain({"model": "m", "max_tokens": 100000, "messages": [{"role": "user", "content": "go"}]})
        print(json.dumps({"finish": finish, "secs": time.time() - t}))
    except Exception as ex:
        print(json.dumps({"error": type(ex).__name__, "secs": time.time() - t}))
''')


def _stub(tmp_path, port, mode):
    path = tmp_path / "stub.py"
    path.write_text(STUB, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, str(path), str(port), mode])
    time.sleep(1.0)
    return proc


def _call(tmp_path, port):
    env = dict(os.environ, RM_LLM="http://127.0.0.1:%d" % port, RM_STATE=str(tmp_path), RM_MIRROR=str(tmp_path),
               RM_CACHE=str(tmp_path), PAPERDAEMON_HOME=str(tmp_path), PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, "-c", CALL % {"root": ROOT}], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd=str(tmp_path))


def test_a_looping_reply_is_stopped_by_repetition(tmp_path):
    stub = _stub(tmp_path, 8791, "loop")
    try:
        out, err = _call(tmp_path, 8791).communicate()
        assert json.loads(out.strip().splitlines()[-1])["finish"] == "runaway", err[-800:]
    finally:
        stub.kill()
        stub.wait()


def test_a_stalled_server_is_waited_for_until_its_process_ends(tmp_path):
    stub = _stub(tmp_path, 8792, "stall")
    call = _call(tmp_path, 8792)
    try:
        time.sleep(8.0)
        assert call.poll() is None                  # still waiting: no clock ended it
    finally:
        stub.kill()                                 # the server's process ends
        stub.wait()
    out, err = call.communicate()
    got = json.loads(out.strip().splitlines()[-1])
    assert got.get("error") or got.get("finish") is None, got
    assert got["secs"] >= 7.0
