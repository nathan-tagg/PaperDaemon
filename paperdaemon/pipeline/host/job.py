"""The job the host is working: one page, its listing, the decision, the steps and the draft, as typed objects.

The host works one job at a time. The job in hand lives in a context variable for as long as the job runs,
never in module state: `begin()` starts one, and `JOB`, a proxy, reads and writes whichever job is current, so
the host's code says `JOB.draw` or `JOB.page` without passing the job through every call.
"""
import contextvars
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Optional

UNSET = object()          # "not looked up yet", where None is a real answer (a page that is no PDF page)


@dataclass
class Item:
    """One listed thing on the page: para:N, line:N, mark:N or picture:N."""
    id: str
    kind: str
    text: str = ""
    box: tuple = ()
    owner: str = ""                     # "user" or "system"
    made: dict = field(default_factory=dict)
    new: bool = False


@dataclass
class Step:
    """One step of a plan, as the host carries it out."""
    id: int
    kind: str
    what: str = ""
    fields: dict = field(default_factory=dict)
    answers: list = field(default_factory=list)
    replaces: Optional[str] = None
    status: str = "pending"
    note: str = ""
    place: Optional[str] = None


@dataclass
class Ruling:
    item: str
    is_: str
    then: str


@dataclass
class Decision:
    kind: str                           # "plan" | "answer" | "ask" | "skip"
    steps: list = field(default_factory=list)
    rulings: list = field(default_factory=list)
    note: str = ""


@dataclass
class Job:
    """Everything one job knows. Fields start empty; the intake, the decision and the steps fill them."""
    # the page
    doc: Optional[str] = None
    page: Optional[int] = None
    page_id: Optional[str] = None
    keys: list = field(default_factory=list)
    frame: Any = UNSET                  # the page's frame in page units (a PDF page is not 1620 wide)
    safe: Any = None                    # the page's safe area (x0, y0, x1, y1), set when the job begins
    pdf_page: Any = UNSET               # (path, index) when the page is a PDF page, else None
    view: Any = None
    sha_start: Optional[str] = None
    sha_commit: Optional[str] = None
    foreign: bool = False               # the page changed under the job
    # the listing the decision turn is shown
    listing: dict = field(default_factory=dict)     # id ("para:1", "line:2", ...) -> {"owner": "user" | "system", "text"}
    new_refs: list = field(default_factory=list)    # the ids of what is new since this system last worked on the page
    paras: list = field(default_factory=list)
    new_paras: Any = None
    kept_paras: set = field(default_factory=set)
    text_col: Any = None
    mark_index: Any = None
    mark_words: Any = None
    new_mark_ids: Any = None
    ink_lines: Any = None
    keys_before: set = field(default_factory=set)
    images: list = field(default_factory=list)
    page_history: Any = None
    sprompt: Any = None
    at_ink: Any = None
    at_tip: Any = None
    at_anchor: Any = None
    # the decision and its steps
    plan: Any = None
    steps: Any = None
    asking: bool = False
    remember: Any = None
    tags: list = field(default_factory=list)
    refused: list = field(default_factory=list)
    found: dict = field(default_factory=dict)
    scratch: dict = field(default_factory=lambda: {"request": None, "searches": [], "notes": [], "restarts": 0})
    reddit_used: dict = field(default_factory=dict)
    history_months: set = field(default_factory=set)
    assisted: list = field(default_factory=list)    # what the harness's assists overrode, for the record
    assists_hinted: set = field(default_factory=set)
    picture_model: Any = None
    pictures: Any = None
    painter_on: Any = None
    # the draft: what the job draws and erases before it commits
    draw: Any = None
    ops: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    hide: dict = field(default_factory=dict)
    hide_typed: list = field(default_factory=list)
    hide_images: list = field(default_factory=list)
    erase_log: Any = field(default_factory=list)
    erased_pictures: dict = field(default_factory=dict)
    figure: Any = None
    last_figure: Any = None
    last_render: Any = None
    written: list = field(default_factory=list)
    extends_to: float = 0
    added_pages: list = field(default_factory=list)
    new_pages: list = field(default_factory=list)
    new_page_notes: dict = field(default_factory=dict)
    # the record
    unseen: bool = False
    looks: int = 0
    turns: int = 0
    model_s: float = 0.0
    ctx_peak: int = 0
    warnings: list = field(default_factory=list)
    notepad: list = field(default_factory=list)
    committed: bool = False
    failed: Any = None
    outcome: Any = None
    note: Any = None

    def take(self, name):
        """A field's value, with the field set back to its starting value."""
        value = getattr(self, name)
        setattr(self, name, _start(name))
        return value


def _start(name):
    f = {x.name: x for x in fields(Job)}[name]
    return f.default_factory() if f.default_factory is not MISSING else f.default


_CURRENT = contextvars.ContextVar("job")


def begin(**known):
    """Start a job: a fresh Job, current from here until the next begin()."""
    job = Job(**known)
    _CURRENT.set(job)
    return job


def current():
    """The job in hand (a fresh one when none has begun, as for a helper called outside a job)."""
    try:
        return _CURRENT.get()
    except LookupError:
        return begin()


class _Proxy:
    """`JOB.x` reads and writes the current job's field x. Holds nothing itself."""
    __slots__ = ()

    def __getattr__(self, name):
        return getattr(current(), name)

    def __setattr__(self, name, value):
        if name not in _NAMES:
            raise AttributeError("a job has no field %r" % name)
        setattr(current(), name, value)

    def clear(self):
        begin()

    def update(self, **known):
        for name, value in known.items():
            setattr(self, name, value)

    def take(self, name):
        return current().take(name)


_NAMES = frozenset(f.name for f in fields(Job))
JOB = _Proxy()
