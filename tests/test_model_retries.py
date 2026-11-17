"""A model that isn't on this computer: its slot's wait for a reply and its retries (11-16, Gemini's 503 "high demand"
skipped jobs after one try)."""
from paperdaemon.models import adapters as A


def _calls(monkeypatch, answers):
    """_request replaced: each call takes the next answer (an AdapterError is raised); the waits and pauses seen."""
    seen = {"timeouts": [], "pauses": []}

    def fake(method, url, body=None, headers=None, timeout=None, raw=False):
        seen["timeouts"].append(timeout)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(A, "_request", fake)
    monkeypatch.setattr(A.time, "sleep", lambda s: seen["pauses"].append(s))
    return seen


def test_a_busy_server_is_asked_again_after_a_pause(monkeypatch):
    seen = _calls(monkeypatch, [A.AdapterError("busy", 503), A.AdapterError("busy", 429, "", 7), {"ok": 1}])
    a = A.OpenAIChat("https://example.com/v1")
    a.retries, a.wait = 3, 90.0
    assert a.call("POST", "https://example.com/v1/chat/completions", {}) == {"ok": 1}
    assert seen["pauses"] == [5.0, 7]                 # (the second pause: what the server asked for)
    assert seen["timeouts"] == [90.0, 90.0, 90.0]


def test_no_reply_is_asked_again_too_and_retries_run_out(monkeypatch):
    seen = _calls(monkeypatch, [A.AdapterError("silent"), A.AdapterError("busy", 503), A.AdapterError("busy", 503)])
    a = A.OpenAIChat("https://example.com/v1")
    a.retries = 2
    try:
        a.call("POST", "https://example.com/v1/chat/completions", {})
        raise AssertionError("expected the last busy answer")
    except A.AdapterError as ex:
        assert ex.status == 503
    assert seen["pauses"] == [5.0, 10.0] and seen["timeouts"] == [None, None, None]


def test_any_other_answer_is_the_answer(monkeypatch):
    seen = _calls(monkeypatch, [A.AdapterError("bad", 400, "tool_choice")])
    a = A.OpenAIChat("https://example.com/v1")
    a.retries = 3
    try:
        a.call("POST", "https://example.com/v1/chat/completions", {})
    except A.AdapterError as ex:
        assert ex.status == 400
    assert seen["pauses"] == []


def test_the_slot_sets_them_for_a_model_away_from_this_computer_only():
    away = A.paced(A.OpenAIChat("https://generativelanguage.googleapis.com/v1beta/openai"),
                   {"api": "openai", "location": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "reply_wait": 120, "retries": 5})
    assert (away.wait, away.retries) == (120.0, 5)
    default = A.paced(A.OpenAIChat("https://api.example.com"), {"api": "openai", "location": "https://api.example.com"})
    assert (default.wait, default.retries) == (None, A.RETRIES)
    here = A.paced(A.OpenAIChat("http://127.0.0.1:8080"), {"api": "openai", "location": "http://127.0.0.1:8080",
                                                           "retries": 5, "reply_wait": 30})
    assert (here.wait, here.retries) == (None, 0)
