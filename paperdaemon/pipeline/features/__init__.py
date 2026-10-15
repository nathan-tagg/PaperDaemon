"""What PaperDaemon can do for a page, as a list of features, each declaring what it needs.

A feature adds step kinds to the plan and tools to the model's turns. Its requirements are of six kinds:
text capabilities, image abilities and workflows, a search provider, installed content, a filled setting,
and other features. A HARD requirement unmet turns the feature off; an OPTIONAL one unmet leaves it on but
degraded (it works without what it lacks). The engine resolves the list for every lineup
(models/lineup.py) and writes each feature's state, with the chain of reasons for an off or degraded one,
into the host's run file; the host offers only what is on.

This module is data and imports only the standard library: the engine reads it without loading the host.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Requires:
    text: dict = field(default_factory=dict)          # capability -> True, a value, or a minimum (numbers)
    image: tuple = ()                                 # image abilities, e.g. ("generate",)
    workflows: tuple = ()                             # image workflows, e.g. ("childrensColoringBook",)
    search: bool = False                              # a search provider is configured
    content: tuple = ()                               # installed content, e.g. ("characters",)
    settings: tuple = ()                              # filled settings, e.g. ("location",)
    features: tuple = ()                              # other features, by name


class Feature:
    name = ""
    summary = ""
    requires = Requires()
    optional = Requires()
    steps = ()              # the step kinds it adds to the plan
    tools = ()              # the tools it serves
    decisions = ()          # the decisions it declares (what a harness's keyword assist may name)


def _f(name, summary, requires=Requires(), optional=Requires(), steps=(), tools=(), decisions=()):
    return type("Feature_" + name, (Feature,), dict(name=name, summary=summary, requires=requires,
                                                     optional=optional, steps=tuple(steps), tools=tuple(tools),
                                                     decisions=tuple(decisions)))


FEATURES = (
    _f("write", "answers in words, lettered on the page", steps=("write",),
       tools=("answer", "write_paragraph", "write_line"), decisions=("item.ruling", "step.kind")),
    _f("erase", "erasing what the page asked to have removed", optional=Requires(features=("point",)),
       steps=("erase",), decisions=("item.ruling",)),
    _f("inspect", "looking closer before deciding", optional=Requires(text={"vision": True}),
       tools=("look_closer", "show_marks", "render", "page_history", "changes", "notepad_read")),
    _f("point", "finding what the user points at", requires=Requires(text={"vision": True}),
       tools=("find",)),
    _f("markup", "highlighting, circling, underlining and striking words", optional=Requires(features=("point",)),
       steps=("highlight", "circle", "underline", "strike"), decisions=("markup.target",)),
    _f("draw", "drawings made of figures and elements", optional=Requires(text={"vision": True}),
       steps=("draw",), tools=("draw_figure", "element", "edit_figure", "undo_last")),
    _f("chart", "charts", steps=("chart",), tools=("chart",)),
    _f("calendar", "a month or a week", requires=Requires(features=("chart",)),
       optional=Requires(settings=("location",)), steps=("calendar",), tools=("history",)),
    _f("posts", "social posts clipped onto the page", requires=Requires(features=("chart",)), steps=("posts",),
       decisions=("posts.source",)),
    _f("search", "looking things up on the web", requires=Requires(search=True), steps=("search",),
       tools=("web_search",)),
    _f("pictures", "pictures placed on the page and new pages for them"),
    _f("image", "pictures made by the image model", requires=Requires(image=("generate",), features=("pictures",)),
       steps=("image",), tools=("image",), decisions=("image.steps", "step.replaces")),
    _f("coloring", "coloring pages", requires=Requires(image=("generate",), features=("pictures",)),
       optional=Requires(workflows=("childrensColoringBook",)), steps=("coloring",)),
    _f("picture_edit", "changing a picture already on the page", requires=Requires(image=("edit_reference",),
                                                                                    features=("image",))),
    _f("web_picture", "pictures found on the web", requires=Requires(features=("search", "pictures")),
       steps=("web_picture",)),
    _f("chess", "chess against a character", requires=Requires(content=("characters", "chess engine")),
       optional=Requires(text={"vision": True}), steps=("chess",)),
    _f("adventure", "an ink adventure", optional=Requires(features=("image", "picture_edit"), text={"vision": True}),
       steps=("adventure",)),
    _f("messages", "a chat with the town's residents", requires=Requires(content=("characters",)),
       optional=Requires(features=("image", "picture_edit"), text={"vision": True}), steps=("messages",)),
    _f("notepad", "the notebook's notepad", tools=("notepad",)),
    _f("tag", "tagging the page when the user asked for it", steps=("tag",)),
)


class CatalogError(ValueError):
    pass


class Catalog:
    """Every feature, by name, checked: every required feature exists and no requirements form a cycle."""

    def __init__(self, features=FEATURES):
        self.by_name = {f.name: f for f in features}
        if len(self.by_name) != len(features):
            raise CatalogError("two features share a name")
        self.check()

    def needs(self, f):
        return tuple(f.requires.features) + tuple(f.optional.features)

    def check(self):
        for f in self.by_name.values():
            for n in self.needs(f):
                if n not in self.by_name:
                    raise CatalogError("the feature %s requires %s, which is not a feature" % (f.name, n))
        state, path = {}, []

        def visit(n):
            if state.get(n) == "done":
                return
            if state.get(n) == "visiting":
                cycle = path[path.index(n):] + [n]
                raise CatalogError("the features form a cycle: %s" % " -> ".join(cycle))
            state[n] = "visiting"
            path.append(n)
            for m in self.needs(self.by_name[n]):
                visit(m)
            path.pop()
            state[n] = "done"
        for n in self.by_name:
            visit(n)

    def order(self):
        """The features, each after the ones it requires."""
        out, seen = [], set()

        def add(n):
            if n in seen:
                return
            seen.add(n)
            for m in self.needs(self.by_name[n]):
                add(m)
            out.append(self.by_name[n])
        for n in self.by_name:
            add(n)
        return out

    def step_feature(self):
        """{step kind: the feature that adds it}."""
        return {s: f.name for f in self.by_name.values() for s in f.steps}

    def to_json(self):
        def req(r):
            return {k: (list(v) if isinstance(v, tuple) else v) for k, v in r.__dict__.items() if v}
        return {f.name: {"summary": f.summary, "requires": req(f.requires), "optional": req(f.optional),
                         "steps": list(f.steps), "tools": list(f.tools)} for f in self.by_name.values()}


def resolve(catalog, facts):
    """Each feature's state, in dependency order: {name: {"state": "on" | "degraded" | "off", "because": [..]}}.

    `facts`: {"text": {capability: value}, "image": [abilities] or None, "workflows": [...], "search": bool,
    "content": [installed], "settings": [filled], "off": {name: why}} -- `off` holds the features the user
    or the harness switched off, with the reason each gives."""
    out = {}

    def unmet(r):
        why = []
        for cap, want in r.text.items():
            have = facts.get("text", {}).get(cap)
            ok = (have >= want) if isinstance(want, (int, float)) and not isinstance(want, bool) else have == want
            if not ok:
                why.append("the text model has no %s" % cap if want is True else "the text model's %s is not %s" % (cap, want))
        image = facts.get("image")
        for a in r.image:
            if image is None:
                why.append("the lineup has no image model")
                break
            if a not in image:
                why.append("the image model cannot %s" % a.replace("_", " "))
        for w in r.workflows:
            if w not in (facts.get("workflows") or ()):
                why.append("the image model has no %s workflow" % w)
        if r.search and not facts.get("search"):
            why.append("no search provider is configured")
        for c in r.content:
            if c not in (facts.get("content") or ()):
                why.append("the %s is not installed" % c)
        for s in r.settings:
            if s not in (facts.get("settings") or ()):
                why.append("no %s is set" % s)
        for n in r.features:
            st = out.get(n)
            if st and st["state"] == "off":
                why.append("%s is off because %s" % (n, "; ".join(st["because"])))
        return why

    for f in catalog.order():
        if f.name in (facts.get("off") or {}):
            out[f.name] = {"state": "off", "because": [facts["off"][f.name]]}
            continue
        hard = unmet(f.requires)
        if hard:
            out[f.name] = {"state": "off", "because": hard}
            continue
        soft = unmet(f.optional)
        out[f.name] = {"state": "degraded", "because": soft} if soft else {"state": "on", "because": []}
    return out
