"""After a game turn, the job's instructions go back into the text model's memory (host.model.keep_prefix): one
request with the job's own system message and tools, one token out, to a server on this computer that keeps slots.
A hosted model is never sent one. A stand-in server on a port of the test's own plays llama.cpp; nothing reaches a
real model."""
import http.server
import json
import socket
import threading

from paperdaemon.pipeline import host as H
from paperdaemon.pipeline.host import model as M


def _server(seen, slots=1):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"total_slots": slots} if self.path == "/props" else {}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            seen.append((self.path, json.loads(self.rfile.read(n).decode())))
            body = json.dumps({"choices": [{"message": {"content": "."}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % port


def _fake_host(monkeypatch, loc):
    monkeypatch.setitem(H.RUN, "text_location", loc)
    monkeypatch.setattr(H, "LLM", loc)
    monkeypatch.setattr(H, "tool_schema", lambda: [{"type": "function", "function": {"name": "plan"}}])

    class Harness(object):
        def system(self, host, doc):
            return "THE BRIEF for %s" % doc
    monkeypatch.setattr(H, "_H", lambda: Harness())
    monkeypatch.setattr(H, "_host", lambda: None)


def test_the_jobs_instructions_go_back_into_a_local_servers_memory(monkeypatch):
    seen = []
    srv, loc = _server(seen)
    try:
        _fake_host(monkeypatch, loc)
        assert M.keep_prefix("doc-1") is True
    finally:
        srv.shutdown()
    (path, body), = seen
    assert path == "/v1/chat/completions" and body["max_tokens"] == 1
    assert body["messages"][0] == {"role": "system", "content": "THE BRIEF for doc-1"}
    assert body["tools"] == [{"type": "function", "function": {"name": "plan"}}]


def test_a_hosted_model_or_a_server_without_slots_is_never_sent_one(monkeypatch):
    _fake_host(monkeypatch, "https://generativelanguage.googleapis.com/v1beta/openai/")
    assert M.keep_prefix("doc-1") is False
    seen = []
    srv, loc = _server(seen, slots=0)
    try:
        _fake_host(monkeypatch, loc)
        assert M.keep_prefix("doc-1") is False
    finally:
        srv.shutdown()
    assert seen == []
