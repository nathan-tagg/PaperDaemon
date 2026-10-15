"""The host works each job on the lineup its tag belongs to: that lineup's values, its tags' prompts in the
Tagging tab's order with the notebook's own instructions last, and its memories."""
import paperdaemon.pipeline.host as H
from paperdaemon import ledger


RUNFILE = {
    "lineup": "A", "capabilities": {"max_output": 100}, "model": "a-model",
    "tag_lineup": {"ask": "A", "draw": "B"},
    "lineups": {"A": {"lineup": "A", "capabilities": {"max_output": 100, "vision": True}, "model": "a-model",
                      "tags": [{"name": "Ask", "prompt": ""}]},
                "B": {"lineup": "B", "capabilities": {"max_output": 200, "vision": False}, "model": "b-model",
                      "tags": [{"name": "Plain", "prompt": "Use plain words."}, {"name": "Draw", "prompt": "Draw boldly."},
                               {"name": "Unused", "prompt": "Never shown."}]}},
    "settings": {"tags": {"ignore": "ignore", "sprompt": "sprompt"}},
}


def _host(monkeypatch, told):
    for name in ("CAPS", "MODEL", "CTX", "_BRIEF", "MAX_TOKENS", "VISION"):   # put back after the test
        monkeypatch.setattr(H, name, getattr(H, name))
    monkeypatch.setattr(H, "_RUN_FILE", RUNFILE)
    monkeypatch.setattr(H, "RUN", dict(RUNFILE))
    monkeypatch.setattr(H, "_CTX_SEEN", {"A": 1000, "B": 2000})
    monkeypatch.setattr(ledger, "TRIGGERS", ["ask", "draw", "plain", "unused"])

    def studio(path, body=None, timeout=None):
        told.append((path, body))
        if path.startswith("/memories?"):
            return {"memories": [{"id": "m1", "text": "Erase my request when done."}], "max": 30}
        return {}
    monkeypatch.setattr(H, "_studio", studio)


def test_a_job_runs_on_the_lineup_of_its_tag(monkeypatch):
    told = []
    _host(monkeypatch, told)
    assert H.lineup_for("Draw: a cat") == "B" and H.lineup_for("nothing") is None
    H.use_lineup("B")
    assert H.MODEL == "b-model" and H.MAX_TOKENS == 200 and H.VISION is False and H.CTX == 2000
    assert ("/lineup", {"name": "B"}) in told                  # the engine sends the job's calls to B's slots
    H.use_lineup("A")
    assert H.MODEL == "a-model" and H.CTX == 1000


def test_the_prompt_is_the_tags_in_tab_order_then_the_notebooks_own(monkeypatch):
    told = []
    _host(monkeypatch, told)
    H.use_lineup("B")
    monkeypatch.setattr(ledger, "content", lambda doc: {"tags": [{"name": "Draw: a cat"}, {"name": "Plain"}],
                                                        "pageTags": [], "cPages": {"pages": []}})
    monkeypatch.setattr(ledger, "meta", lambda doc: {"parent": ""})
    monkeypatch.setattr(H, "notebook_prompt", lambda doc: "Answer in French.")
    H.JOB.clear()
    try:
        out = H.notebook_system("doc")
    finally:
        H.JOB.clear()
    plain, draw, sp = out.index("Use plain words."), out.index("Draw boldly."), out.index("Answer in French.")
    assert plain < draw < sp and "Never shown." not in out


def test_the_lineups_memories_are_shown_and_changed(monkeypatch):
    told = []
    _host(monkeypatch, told)
    monkeypatch.setenv("RM_STUDIO", "http://127.0.0.1:1/host")
    H.use_lineup("B")
    got = H.memories_system()
    assert "YOUR MEMORIES" in got and "m1: Erase my request when done." in got
    assert told[-1][0] == "/memories?lineup=B"
    remember = H.REMEMBER
    assert all("remember" in dict((n, p) for n, _, p, _ in H.TOOLS)[d] for d in H.PLAN_TOOLS)
    assert list(remember["items"]["properties"]) == ["text"]   # one declared key: the grammar keeps key order


def test_what_is_off_is_not_offered(monkeypatch):
    """A lineup's features decide the brief's steps and the tools: an off feature's step and tools are gone."""
    off = {"state": "off", "because": ["no image model"]}
    for name in ("CAPS", "MODEL", "CTX", "_BRIEF", "MAX_TOKENS", "VISION", "_SCHEMA"):
        monkeypatch.setattr(H, name, getattr(H, name))
    monkeypatch.setattr(H, "RUN", dict(H.RUN, features={"image": off, "coloring": off, "search": off,
                                                         "web_picture": off, "chess": off, "adventure": off,
                                                         "messages": off}))
    monkeypatch.setattr(H, "_BRIEF", None)
    monkeypatch.setattr(H, "_SCHEMA", None)
    brief = H.system_brief()
    steps = [ln.split()[0] for ln in brief.split("\n") if ln.startswith("  ") and not ln.startswith("   ")]
    for gone in ("image", "coloring", "search", "web_picture", "game"):
        assert gone not in steps, gone
    for kept in ("write", "chart", "draw", "erase"):
        assert kept in steps, kept
    assert "kanban, checklist" in brief                      # a kept step keeps its continuation line
    names = [t["function"]["name"] for t in H.tool_schema()]
    assert "web_search" not in names and "image" not in names and "write_paragraph" in names
