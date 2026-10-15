"""The text harness as an interface the host calls.

A text harness says what differs between models: what the model is shown and told (intake), what its replies
mean (output), how the host's small questions about a page are asked and read (the assist protocols), what is
refused or fixed before a commit (validate), how a conflict between the tablet and a job is put to the model
(conflict), what the model is told about each job and tool (skills), and what it needs and supports (declare).

The class here IS PaperDaemon's built-in default: every method is today's behavior. A harness in the user's
`llm` folder subclasses it and overrides only what it changes. The host sends every turn a harness builds and
hands the raw reply back to the same harness; a harness never calls a model, the network or the files itself.

Every method gets `host`, the host module: its readings of the page and its constants. A harness reads from it
and never writes through it.
"""
import json
import os
import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------- what passes between the host and a harness

@dataclass
class Turn:
    """One turn the host sends: the conversation so far, the calls that may answer it, and how it is asked."""
    messages: list
    allowed: tuple
    tries: int = 3
    choice: str = "required"
    accept_prose: bool = False
    final: tuple = None
    temperature: float = None


@dataclass
class Call:
    """One call read from a reply: its id, its name, its arguments, or why they could not be read."""
    id: str
    name: str
    args: dict = None
    error: str = None


# what the decision's reply means: exactly one of these
@dataclass
class Jobs:
    """Carry out the jobs the plan made (the host holds them in the job's steps)."""
    note: str = ""


@dataclass
class Skip:
    """Nothing to do, and why (None: the reply already recorded it)."""
    why: str = None


@dataclass
class FinishedPage:
    """A model that did the whole job itself, as what changes on the page: the strokes it adds
    ([{"points": [[x, y], ...], "width": n}], page units, x 0 at the center), what it erases (the listing's ids,
    each {"id", "because"}), the pictures it made ([{"png": a path, "box": [x0, y0, x1, y1]}]) and a line saying
    what it did. The host erases, writes and commits it through its own commit, like any job; nothing of the
    user's comes off unless its id is listed."""
    strokes: list = field(default_factory=list)
    erase: list = field(default_factory=list)
    pictures: list = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------- the default's prompts for the assist protocols

LOCATE_MANY = ("This is a page from a tablet notebook. Locate each of these on it:\n{items}\n"
               "Answer with JSON, one entry per item, in order: [{{\"n\": 1, \"bbox_2d\": [x1, y1, x2, y2]}}, "
               "{{\"n\": 2, \"point_2d\": [x, y]}}, ...] -- bbox_2d round a thing, point_2d for a spot on "
               "empty paper, or {{\"n\": 3, \"not_found\": true}}. An item that asks what an arrow POINTS AT "
               "is the thing at the arrow's head -- not the arrow, not the words at its tail. An item that "
               "asks for an ARROW ITSELF is the arrow's own line and head.")
LOCATE_ONE = ('Locate the {what} in this image. Output its bounding box in JSON, like '
              '[{{"bbox_2d": [x1, y1, x2, y2], "label": "{what}"}}]. '
              'If it is not in the image, say NOT FOUND.')


class TextProtocols:
    """The interface, with PaperDaemon's own behavior for every method."""

    # the job kinds this harness supports (None: every kind), and abilities its model provides itself
    kinds = None
    provides = ()
    # job kind -> a protocol replacing the host's (rare; the host holds the protocols)
    protocols = {}
    # where this harness's skill files are (None: the default's skills are the host's text)
    skills_dir = None
    # what the decision turn may spend on looking (inspection results plus what the model writes), in tokens
    inspect_tokens = 12000
    # keyword assists (harnesses/schema.py): none in any shipped harness
    assists = ()

    # ------------------------------------------------------------ declare
    @classmethod
    def declare(cls):
        """Its needs and what it supports, for the capacity engine. Nothing runs."""
        return {"kinds": sorted(cls.kinds) if cls.kinds is not None else None, "provides": sorted(cls.provides)}

    # ------------------------------------------------------------ skills
    def skill(self, name, default=""):
        """What the model is told about a job kind or tool: the harness's skill file of that name, else the
        default's text."""
        if self.skills_dir:
            p = os.path.join(self.skills_dir, re.sub(r"[^A-Za-z0-9_-]", "", str(name)) + ".md")
            try:
                with open(p, encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
        return default

    # ------------------------------------------------------------ intake
    def route(self, host, doc, page_id):
        """A page whose job is known before any turn: a page holding a game is a GAME_TURN (its game engine
        reads the move and the character answers), with no decision. -> a JobKind, or None to decide."""
        from paperdaemon.pipeline import games as GM
        from paperdaemon.pipeline.host.jobs import JobKind
        return JobKind.GAME_TURN if GM.game_on_page(doc, page_id) is not None else None

    def system(self, host, doc):
        """The system message: the brief (static, cached), the lineup's memories, the notebook's prompt word
        for word."""
        return self.skill("brief", host.system_brief()) + host.memories_system() + host.notebook_system(doc)

    def step_skill(self, do):
        """What the model is told about one kind of job, added to that job's turn ("" in the built-in default:
        its brief says it all)."""
        return self.skill(do, "")

    def intake(self, host, doc, page, name, wake):
        """The first turn's messages: the system message, then the page as the model sees it with `wake` (the
        host's reading of the page, in words)."""
        return [{"role": "system", "content": self.system(host, doc)}, host.page_image(doc, page, wake)]

    def decision(self, host, msgs):
        """The turn that decides: skip, answer, ask or plan."""
        return Turn(msgs, tuple(host.PLAN_TOOLS), tries=3, temperature=host.DECIDE_TEMP)

    # ------------------------------------------------------------ output
    def calls(self, message):
        """The calls in one reply (a model that writes its calls in prose would find them here)."""
        return message.get("tool_calls") or []

    def read_call(self, c, cut):
        """One call -> Call, with its arguments read, or the error that goes back to the model."""
        cid = c.get("id", "x")
        fn = c["function"]["name"]
        try:
            args = json.loads(c["function"]["arguments"] or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments are not an object")
        except Exception:
            why = ("your call was CUT OFF because it was too long -- send fewer parts, or split "
                   "it across two calls" if cut else "arguments were not valid JSON")
            return Call(cid, fn, None, why)
        return Call(cid, fn, args)

    def nudge_runaway(self, said, allowed):
        """What goes back after a reply that ran on in prose and was cut off."""
        return [{"role": "assistant", "content": (said[:300] + " ...") if said else "..."},
                {"role": "user", "content": "Your last reply ran on in prose and was cut off. No prose: make the call, "
                                            "one of %s." % ", ".join(allowed)}]

    def nudge_no_call(self, said, allowed):
        """What goes back after prose where a call was wanted (SHORT: a long reply once cost 16k prompt tokens)."""
        return [{"role": "assistant", "content": ((said[:400] + " ...") if len(said) > 400 else said) or "(nothing)"},
                {"role": "user", "content": "Make the call now -- one of %s. Prose is not an outcome." % ", ".join(allowed)}]

    def nudge_refused(self, allowed):
        """The tool result for a call that is not allowed right now."""
        return {"error": "not now. Right now the call is one of: %s." % ", ".join(allowed)}

    def nudge_gathered(self, allowed):
        """What goes back after a round that only gathered (a helper call) and did not do the step."""
        return {"role": "user", "content": "You have what you gathered. Now make the step's "
                                           "call: one of %s." % ", ".join(sorted(allowed))}

    def outcome(self, fn, args, res):
        """What the decision's call means for the job."""
        if fn is None:
            return Skip("no decision: %s" % (res or {}).get("error", "?"))
        if fn == "skip":
            return Skip(None)                    # skip() recorded it
        return Jobs()

    # ------------------------------------------------------------ assist protocols
    def locate_many(self, host, items, png_bytes):
        """The request that finds several things at once on a page picture."""
        import base64
        text = "\n".join("%d. %s" % (i + 1, str(w)[:160]) for i, w in enumerate(items))
        return {"model": host.MODEL, "max_tokens": 60 + 60 * len(items), "temperature": 0.2,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": LOCATE_MANY.format(items=text)},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png_bytes).decode()}}]}]}

    def read_located(self, reply, n):
        """The reply to locate_many -> one entry per item: ("box", (x0, y0, x1, y1)) or ("point", (x, y)) as
        fractions of the picture (0..1), or None."""
        got = [None] * n
        for k, obj in enumerate(re.findall(r"\{[^{}]*\}", reply)):
            m = re.search(r'"n"\s*:\s*(\d+)', obj)
            i = int(m.group(1)) - 1 if m else k
            if not (0 <= i < n) or "not_found" in obj:
                continue
            b = re.search(r'"bbox(?:_2d)?"\s*:\s*\[([^\]]+)\]', obj)
            p = re.search(r'"point(?:_2d)?"\s*:\s*\[([^\]]+)\]', obj)
            v = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", (b or p).group(1))] if (b or p) else []
            if b and len(v) == 4:
                got[i] = ("box", tuple(x / 1000.0 for x in v))
            elif p and len(v) == 2:
                got[i] = ("point", tuple(x / 1000.0 for x in v))
        return got

    def locate_one(self, host, what, png_bytes):
        """The request that finds one thing on a page picture."""
        import base64
        return {"model": host.MODEL, "max_tokens": 220, "messages": [{"role": "user", "content": [
            {"type": "text", "text": LOCATE_ONE.format(what=str(what)[:120])},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png_bytes).decode()}}]}]}

    def read_located_one(self, reply, iw, ih):
        """The reply to locate_one -> None when it was not there, else its boxes in the picture's pixels."""
        if "NOT FOUND" in reply.upper():
            return None
        raw = []
        for m in re.finditer(r'"bbox(?:_2d)?"\s*:\s*\[([^\]]+)\]', reply):
            v = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
            if len(v) == 4:
                raw.append(v)
        if not raw:
            for m in re.finditer(r"[\(\[]([^\)\]]*)[\)\]]", reply):
                v = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m.group(1))]
                if len(v) == 4:
                    raw.append(v)
        out = []
        for x0, y0, x1, y1 in raw:
            norm = max(x0, y0, x1, y1) <= 1000.0 and (iw > 1000 or ih > 1000)
            sx = (iw / 1000.0) if norm else 1.0
            sy = (ih / 1000.0) if norm else 1.0
            out.append((x0 * sx, y0 * sy, x1 * sx, y1 * sy))
        return out

    def ask(self, host, content, max_tokens, temperature):
        """The request for one plain reply (no tools): a game's line, a reading of a picture."""
        return {"model": host.MODEL, "max_tokens": int(max_tokens), "temperature": temperature,
                "messages": [{"role": "user", "content": content}],
                "chat_template_kwargs": {"enable_thinking": False}}

    def describe(self, host, path):
        """A picture in words, for a model that cannot see it: the OCR'd lines with their places."""
        return host.describe_png(path)

    # ------------------------------------------------------------ validate
    def validate(self, host, staged):
        """What is refused before commit -> [problem, ...]. The host's own checks (the safe area, the stroke
        limit) always run as well; a harness adds to them and never removes them."""
        return []

    # ------------------------------------------------------------ conflicts
    def conflict(self, host, yours_png, ours_png, made_by):
        """The turn that puts a conflict to the model: the user's page and the job's page as pictures, and the
        job that made the job's page. Its reply is read through output() like a decision."""
        note = ("THE TABLET AND A JOB CHANGED THIS PAGE AT ONCE. The first picture is the page as the user left "
                "it: it stays, and anything you do happens on it. The second is the page as the job had made it, "
                "which was set aside. The job was: %s\nDecide what the user's page still needs from that job, "
                "given what they wrote since, and plan only that -- or skip if it needs nothing." % made_by)
        return [host.image_message(yours_png, note), host.image_message(ours_png, "The page as the job had made it.")]


__all__ = ["Turn", "Call", "Jobs", "Skip", "FinishedPage", "TextProtocols", "LOCATE_MANY", "LOCATE_ONE"]
