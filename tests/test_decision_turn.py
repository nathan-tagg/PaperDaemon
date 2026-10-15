"""The decision turn's looking: bounded by tokens (what the looks add and what the model writes), never by a count
or a clock; the same look twice is refused as already shown; past the budget, the model is told to decide."""
import json

import paperdaemon.pipeline.host as H


def _call(name, args, i=0):
    return {"content": "", "tool_calls": [{"id": "c%d" % i, "type": "function",
                                           "function": {"name": name, "arguments": json.dumps(args)}}]}


def _run(monkeypatch, replies, step_tokens=100):
    sent, served = [], []
    state = {"prompt": 1000}

    def chat(msgs, tool_choice="required", temperature=None):
        sent.append([dict(m) for m in msgs])
        m = replies.pop(0)
        state["prompt"] += step_tokens
        return m, {"prompt_tokens": state["prompt"], "completion_tokens": 20}, False

    def serve(fn, args, cid, msgs, doc, page):
        served.append((fn, args))
        msgs.append({"role": "tool", "tool_call_id": cid, "content": "{}"})
    monkeypatch.setattr(H, "chat", chat)
    monkeypatch.setattr(H, "_serve_look", serve)
    H.JOB.clear()
    out = H._turn([{"role": "user", "content": "decide"}], tuple(H.PLAN_TOOLS))
    return out, sent, served


def test_a_repeated_look_is_refused_as_already_shown(monkeypatch):
    monkeypatch.setitem(H.DISPATCH, "skip", lambda note: {"ok": True})
    out, sent, served = _run(monkeypatch, [_call("changes", {}), _call("changes", {}, 1), _call("skip", {"note": "nothing"}, 2)])
    assert served == [("changes", {})]
    refusal = [m for m in sent[-1] if m.get("role") == "tool" and "already shown" in m["content"]]
    assert refusal and out[0] == "skip"


def test_past_the_budget_the_model_is_told_to_decide(monkeypatch):
    monkeypatch.setitem(H.DISPATCH, "skip", lambda note: {"ok": True})
    monkeypatch.setattr(H.HT.TextProtocols, "inspect_tokens", 150)
    out, sent, served = _run(monkeypatch, [_call("page_history", {"back": 1}), _call("page_history", {"back": 2}, 1),
                                           _call("skip", {"note": "nothing"}, 2)], step_tokens=200)
    assert served == [("page_history", {"back": 1})]          # the second look came after the budget was spent
    assert any(m.get("role") == "tool" and "budget is spent" in m["content"] for m in sent[-1])
    assert out[0] == "skip"
