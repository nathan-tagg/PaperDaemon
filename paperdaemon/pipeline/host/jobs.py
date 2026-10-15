"""The job kinds, one enumerated list, and the protocol the host holds for each.

A plan is a list of jobs; every job is one of these kinds, so the host always knows what to do with it. A
kind's protocol says whether the model has a turn of its own for it (and which calls may answer that turn),
and whether what comes of it goes back to the model. Most kinds need no model turn at all: what the model had
to say came in the plan, and the host does the rest with plain code. A harness may replace a kind's protocol
(its `protocols` mapping); PaperDaemon's own harness does not.

A job is written in the plan with the model's word for it (`do`): the protocols are keyed by that word.
"""
from dataclasses import dataclass
from enum import Enum


class JobKind(Enum):
    ERASE = "erase"
    SEARCH = "search"
    WRITE = "write"
    CHART = "chart"
    CALENDAR = "calendar"
    POSTS = "posts"                  # social posts clipped onto the page
    DRAW = "draw"
    IMAGE = "image"
    COLORING = "coloring"
    PICTURE_EDIT = "picture_edit"    # an image job that names a source picture
    WEB_PICTURE = "web_picture"
    HIGHLIGHT = "highlight"
    CIRCLE = "circle"
    UNDERLINE = "underline"
    STRIKE = "strike"
    GAME_START = "game"              # a chess, adventure or messages step
    GAME_TURN = "game_turn"          # a turn on a game page
    TAG = "tag"
    NOTE = "note"                    # a line kept in the notebook's notepad (the notepad tool)
    REMEMBER = "remember"            # the lineup's memories (the decision's `remember`)
    CONFLICT = "conflict"            # the tablet and a job changed one page


LOOK_TOOLS = ("show_marks", "look_closer", "find", "render", "page_history", "changes", "notepad_read")
# (served, then the turn is asked again)


@dataclass(frozen=True)
class JobProtocol:
    """Who does what in one kind of job."""
    model_turn: bool = False         # the model gets a turn of its own for this job
    allowed: tuple = ()              # the calls that may answer that turn (helpers included)
    closes: tuple = ()               # the calls that DO the job (the turn ends on one of them)
    back_to_model: bool = False      # what the job produced goes into later turns
    exact: bool = False              # asked at the decision's low temperature (a spec, not prose)


_HOST = JobProtocol()

PROTOCOLS = {
    "erase": _HOST,
    "search": JobProtocol(back_to_model=True),
    "write": JobProtocol(True, ("write_paragraph", "write_line", "need_step"),
                         ("answer", "ask", "write_line", "write_paragraph")),
    "chart": JobProtocol(True, ("chart", "history", "web_search", "need_step"), ("chart",), exact=True),
    "calendar": JobProtocol(True, ("chart", "history", "need_step"), ("chart",), exact=True),
    "draw": JobProtocol(True, ("draw_figure", "element", "image", "need_step") + LOOK_TOOLS,
                        ("element", "draw_figure", "edit_figure", "image")),
    "image": _HOST, "coloring": _HOST, "web_picture": _HOST,
    "highlight": _HOST, "circle": _HOST, "underline": _HOST, "strike": _HOST,
    "chess": _HOST, "adventure": _HOST, "messages": _HOST, "posts": _HOST, "tag": _HOST,
    "game_turn": JobProtocol(True), "note": _HOST, "remember": _HOST,
    "conflict": JobProtocol(True),
}

# what closes a step when the model makes the call, for the kinds that close on a call (the image tool closes an
# image step a model turn asked for)
CLOSES = {k: p.closes for k, p in PROTOCOLS.items() if p.closes}
CLOSES["image"] = ("image",)


def kind_of(step):
    """The JobKind of a plan's step (its `do`, and for a chart or an image what it is)."""
    do = step.get("do")
    if do == "image" and step.get("source"):
        return JobKind.PICTURE_EDIT
    if do in ("chess", "adventure", "messages"):
        return JobKind.GAME_START
    return JobKind(do)


def protocol(do, harness=None):
    """The protocol for a job written `do`: the harness's own when it replaces the host's, else the host's."""
    own = getattr(harness, "protocols", None) or {}
    return own.get(do) or PROTOCOLS.get(do) or _HOST


__all__ = ["JobKind", "JobProtocol", "PROTOCOLS", "CLOSES", "LOOK_TOOLS", "kind_of", "protocol"]
