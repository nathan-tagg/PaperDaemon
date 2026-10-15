"""The host's calls to the engine: model turns (streamed, stopped by tokens and repetition), plain asks, and the engine's own routes."""
import os
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from PIL import Image
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H

STUDIO_TOKEN = os.environ.get("RM_STUDIO_TOKEN", "")
_H_MADE = {}
NOTHINK = False                 # the harness's request data switches thinking off, in the engine
PROSE_CAP = 1500          # characters of prose a must-call turn may produce before it is cut
# A RUNAWAY GUARD, NOT A SIZE: the plain asks (games, readings) stop at this many tokens only so a
# looping model cannot run forever (runaway is tokens, never seconds). They were sized to their
# first callers -- 120 for the vision read of a chess move, one line; 300 for text -- and every later
# caller (an adventure's JSON ruling, a long handwritten message) was cut off without a word. A
# caller may ask for less; a cut-off answer is logged.
ASK_MAX_TOKENS = 1500


# --------------------------------------------------------------- the server
def server_up(timeout=3):
    try:
        with urllib.request.urlopen(H.LLM + "/health", timeout=timeout) as r:
            return b'"ok"' in r.read()
    except Exception:
        return False


def ensure_server():
    """Can a model call be served? The engine answers: the text server is up, or its start script can
    start it, which the engine does on the first call (and that call fails if the server's process ends).
    No clock: the call itself waits for the model."""
    if H.server_up():
        return True
    H.log("the text slot cannot be reached through the engine")
    return False


def _studio_open(path, body=None, timeout=None):
    headers = {"Content-Type": "application/json"}
    if STUDIO_TOKEN:
        headers["Authorization"] = "Bearer " + STUDIO_TOKEN

    req = urllib.request.Request(H.STUDIO + path,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def _studio(path, body=None, timeout=None):
    return json.loads(H._studio_open(path, body, timeout).read())


def _H():
    """The text harness this job runs on (the lineup's, else PaperDaemon's built-in default): what the model is
    shown and told, how its replies read, how the host's small questions are asked."""
    from paperdaemon import harnesses as HS
    hid = H.RUN.get("id") or "default-text"
    if hid not in _H_MADE:
        cls = HS.get(hid) or HS.DEFAULT["text"]
        _H_MADE[hid] = cls()
    return _H_MADE[hid]


def _host():
    """The host, as the harness reads it."""
    return H


def _harness():
    """The run file's values (the text harness's id, name, lineup, capabilities and brief additions, what the
    image harness offers, the resolved features): empty when the host runs without the engine."""
    return H.RUN


def chat(messages, tool_choice="required", temperature=None):
    """One turn, STREAMED. Returns (message, usage, truncated).

    Every token is watched as it arrives: a reply that starts repeating itself is cut off here, at once, by
    closing the connection (the server abandons the generation when the client goes), and the model is told.
    That is the runaway guard -- tokens and loops, never seconds. There is no clock on the call.

    tool_choice="required" makes the reply a tool call, always; "auto" is used for the one turn where prose
    means "ok".
    """
    body = {"model": H.MODEL, "max_tokens": H.MAX_TOKENS, "tools": H.tool_schema(),
            "tool_choice": tool_choice if H.TOOL_CHOICE_OK else "auto", "messages": messages,
            "stream": True, "stream_options": {"include_usage": True}}
    if temperature is not None:
        body["temperature"] = float(temperature)
    if NOTHINK:
        # some models ignore the server's reasoning flag; their chat template's own switch works, provided
        # the server was given a template that knows tools at all.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(H.LLM + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    JOB.turns = JOB.turns + 1
    _t0 = time.time()
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as ex:
        txt = ex.read().decode("utf-8", "replace")[:300]
        if ex.code == 400 and "tool_choice" in txt and H.TOOL_CHOICE_OK:
            H.TOOL_CHOICE_OK = False
            H.log("  this server does not take tool_choice=%r (%s) -- using auto" % (tool_choice, txt[:80]))
            return chat(messages, "auto")
        raise RuntimeError("HTTP %d: %s" % (ex.code, txt))
    content, reasoning, calls = [], [], {}
    finish, usage, timings, runaway, n = None, {}, {}, False, 0
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                d = json.loads(data)
            except Exception:
                continue
            if d.get("usage"):
                usage = d["usage"]
            if d.get("timings"):
                timings = d["timings"]
            for ch in d.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    content.append(delta["content"])
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
                for tc in delta.get("tool_calls") or []:
                    i = tc.get("index", 0)
                    slot = calls.setdefault(i, {"id": None, "name": "", "args": []})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name") and not slot["name"]:
                        slot["name"] = f["name"]
                    if f.get("arguments"):
                        slot["args"].append(f["arguments"])
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
            n += 1
            if n % 24 == 0:
                prose = "".join(reasoning[-300:]) + "".join(content[-300:])
                args = "".join(a for sl in calls.values() for a in sl["args"][-300:])
                # A TURN THAT MUST END IN A CALL has no use for more than a paragraph of prose. The
                # server does not enforce tool_choice="required" with this model's tool format, and
                # a reply that answered in prose instead ran 16,384 tokens -- 512 s -- without ever
                # repeating a 40-character tail exactly. Cut at the length, not the clock.
                if tool_choice == "required" and not calls and sum(len(c) for c in content) > PROSE_CAP:
                    runaway = True
                    break
                if H._runaway(prose) or H._looping(args):
                    runaway = True
                    break                       # leaving the `with` closes the socket: the server stops
    msg = {"role": "assistant", "content": "".join(content) or None}
    if calls:
        msg["tool_calls"] = [{"id": sl["id"] or ("call_%d" % i), "type": "function",
                              "function": {"name": sl["name"], "arguments": "".join(sl["args"])}}
                             for i, sl in sorted(calls.items())]
    if isinstance(msg["content"], str) and "</think>" in msg["content"]:
        msg["content"] = msg["content"].rpartition("</think>")[2].strip()
    usage = dict(usage or {})
    usage["timings"] = timings
    usage["runaway"] = runaway
    usage["reasoning_chars"] = sum(len(r) for r in reasoning)
    JOB.model_s = JOB.model_s + (time.time() - _t0)      # what the MODEL cost
    if runaway:
        # WHAT it was repeating -- a chart call was cut at 120 chunks and the log could not say
        # whether that was a real loop or the guard misfiring on a legal spec
        _tail = ("".join(a for sl in calls.values() for a in sl["args"]) or "".join(content))[-160:]
        H.log("  RUNAWAY cut off after %d chunks (%d chars of reasoning, %d of content, %d calls); "
            "it ended: %r" % (n, usage["reasoning_chars"], sum(len(c) for c in content), len(calls), _tail))
        msg["tool_calls"] = None                # whatever was mid-way is not a call
    if timings:
        H.log("  turn: %s prompt tok (%s cached) in %.1fs, %s out in %.1fs"
            % (timings.get("prompt_n"), timings.get("cache_n", "?"),
               (timings.get("prompt_ms") or 0) / 1000.0, timings.get("predicted_n"),
               (timings.get("predicted_ms") or 0) / 1000.0))
    return msg, usage, (finish == "length") or runaway


def _runaway(text, chunk=40, times=6):
    """True when PROSE has degenerated into repeating itself: the last 40 characters occur six
    or more times in the recent text."""
    t = (text or "").strip()[-6000:]
    if len(t) < chunk * times:
        return False
    tail = t[-chunk:]
    return t.count(tail) >= times


def _looping(text, times=6):
    """True when a TOOL CALL's arguments have started repeating a chunk back to back. Stricter
    than _runaway on purpose: a hundred-part figure legitimately says '"kind": "line"' a hundred
    times, so only a chunk repeated CONTIGUOUSLY counts."""
    t = (text or "")[-4000:]
    if len(t) < 240:
        return False
    for L in range(3, 151):                    # every period: a 23-char part repeats with period 23
        tail = t[-L:]
        if tail.strip() and t.endswith(tail * times):
            return True
    return False


def plain(body):
    """One reply without tools (the games' asks, the readings, grounding), STREAMED and stopped by the same
    runaway guard as a turn -- tokens and repetition, never a clock. -> (text, finish reason)."""
    body = dict(body, stream=True)
    req = urllib.request.Request(H.LLM + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    content, reasoning, finish, n = [], [], None, 0
    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                d = json.loads(data)
            except ValueError:
                continue
            for ch in d.get("choices") or []:
                delta = ch.get("delta") or {}
                content.append(delta.get("content") or "")
                reasoning.append(delta.get("reasoning_content") or "")
                finish = ch.get("finish_reason") or finish
            n += 1
            if n % 24 == 0 and H._runaway("".join(reasoning[-300:]) + "".join(content[-300:])):
                H.log("  RUNAWAY plain reply cut off after %d chunks" % n)
                finish = "runaway"
                break
    text = "".join(content) or "".join(reasoning)
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip(), finish


# --------------------------------------------------------------- games (rm_games, rm_chess)
def _llm_up():
    """Is the text model answering? A game plays without it; only its talk and written moves wait."""
    try:
        with urllib.request.urlopen(H.LLM + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ask(content, max_tokens=None, temperature=0.6):
    """One plain reply from the text model: no tools (the harness writes the request). -> text"""
    body = H._H().ask(H._host(), content, int(max_tokens or ASK_MAX_TOKENS), temperature)
    t = time.time()
    text, finish = H.plain(body)
    JOB.model_s = JOB.model_s + time.time() - t
    JOB.turns = JOB.turns + 1
    if finish == "length":
        H.log("  the model's answer hit the %d-token guard and was cut off" % body["max_tokens"])
    return text


def _ask_text(prompt, max_tokens=None, temperature=0.6):
    return H._ask(prompt, max_tokens=max_tokens, temperature=temperature)


def _ask_vision(prompt, png, max_tokens=None, temperature=0.1):
    """The model's reading of a picture (a page render, a kept scene), asked with a prompt."""
    import base64 as _b64
    im = Image.open(png).convert("RGB")
    im.thumbnail((1300, 1300))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return H._ask([{"type": "text", "text": prompt},
                 {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()}}],
                max_tokens=max_tokens, temperature=temperature)
