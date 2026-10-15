"""Test this model: what a slot can actually do, one check at a time.

Text: the endpoint answers and lists its models; the model replies; a forced tool call works; the model
can see (one small synthetic picture of a colored square, the only image ever sent to a slot whose
vision is off). Image: the endpoint answers; a small render comes back and is shown, never kept.

A check that disagrees with the slot's effective capabilities becomes a suggestion; the test never
changes a setting by itself.

The test is a model call like any other: it goes through card.call, so the model's start script runs
first when PaperDaemon's own server is not running, and no start script runs while it is in progress.
"""
import base64
import random
import struct
import zlib

from .. import settings as S
from . import adapters, slots

RECORD = {"name": "record", "description": "Record one word.",
          "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]}}
COLORS = {"red": (220, 30, 30), "green": (30, 170, 60), "blue": (30, 70, 220)}

_last = {"text": None, "image": None}      # the latest report per slot, in memory only


def square_png(rgb, size=64):
    """A PNG of one solid colored square, made without an image library."""
    row = b"\x00" + bytes(rgb) * size
    raw = row * size

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _check(report, name, fn, role=None):
    from .. import card
    try:
        if role:
            with card.call(role):
                ok, detail = fn()
        else:
            ok, detail = fn()
    except adapters.AdapterError as ex:
        ok, detail = False, str(ex)
    except Exception as ex:                        # a test reports; it never crashes the engine
        ok, detail = False, "%s: %s" % (type(ex).__name__, ex)
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    return ok


def test_text(s=None):
    report = {"slot": "text", "lineup": S.active(s)["name"], "checks": [], "suggest": {}}
    if not slots.configured("text", s):
        report["checks"].append({"name": "Location", "ok": False, "detail": "the text slot has no location"})
        return report
    a = adapters.for_slot("text", s)
    caps, prof = slots.caps("text", s), slots.harness("text", s)

    def listing():
        names = a.models()
        slots.report_models("text", names)
        report["reported"] = names
        return True, ", ".join(names[:6]) or "answers, lists no models"
    if not _check(report, "Endpoint answers", listing, "text"):
        return report

    def reply():
        r = a.chat("You are being checked to see that you answer.",
                   [{"role": "user", "text": "Reply with the single word: ready"}], caps=caps, harness=prof,
                   temperature=0)
        return "ready" in r["text"].lower(), (r["text"].strip()[:80] or "an empty reply")
    _check(report, "Replies", reply, "text")

    found = {}

    def forced():
        r = a.chat("Use the tool you are given.", [{"role": "user", "text": "Record the word: apple"}],
                   tools=[RECORD], force_tool=True, caps=dict(caps, forced_tool=True), harness=prof, temperature=0)
        ok = bool(r["tool_calls"]) and r["tool_calls"][0]["name"] == "record" and not r["forced_refused"]
        found["forced_tool"] = ok
        if r["forced_refused"]:
            return False, "the server refused to force a tool call"
        return ok, "called record" if ok else "answered without calling the tool"
    _check(report, "Forced tool call", forced, "text")

    def vision():
        color = random.choice(list(COLORS))
        r = a.chat("You are being checked to see whether you can see pictures.",
                   [{"role": "user", "text": "What color is the square in this picture? Answer with one word: "
                                             "red, green or blue.", "images": [square_png(COLORS[color])]}],
                   caps=dict(caps, vision=True), harness=prof, temperature=0)
        said = r["text"].lower()
        ok = color in said and not any(c in said for c in COLORS if c != color)
        found["vision"] = ok
        return ok, "named the %s square" % color if ok else "the square was %s; it said %r" % (color, r["text"][:40])
    _check(report, "Sees pictures", vision, "text")

    report["suggest"] = {k: v for k, v in found.items() if caps.get(k) != v}
    _last["text"] = report
    return report


def test_image(s=None):
    report = {"slot": "image", "lineup": S.active(s)["name"], "checks": [], "suggest": {}}
    if not slots.configured("image", s):
        report["checks"].append({"name": "Location", "ok": False, "detail": "the image slot has no location"})
        return report
    a = adapters.for_slot("image", s)
    caps, prof = slots.caps("image", s), slots.harness("image", s)

    def listing():
        names = a.models()
        slots.report_models("image", names)
        report["reported"] = names
        return True, ", ".join(n for n in names[:6] if n) or "answers, lists no models"
    if not _check(report, "Endpoint answers", listing, "image"):
        return report

    def render():
        w, h = slots.picture_size(caps, 512, 512, prof.size_multiple)
        png = a.generate("a simple drawing of a house on a hill", w, h, caps["steps"],
                         caps["cfg"], caps["sampler"], caps["scheduler"], random.randint(0, 2 ** 31 - 1),
                         caps["shift"])
        report["picture"] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        return True, "%d x %d, %d steps" % (w, h, caps["steps"])
    _check(report, "Makes a picture", render, "image")
    # the picture lives only in this in-memory report, which the next test replaces
    _last["image"] = report
    return report


def last(role):
    return _last.get(role)
