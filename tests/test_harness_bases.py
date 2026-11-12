"""The three harness bases a lineup's text model runs on (Weak, Medium, Strong), and what a model can do on its own:
search the web, make an image. The lineup's own search is used when it has one; the model's own search only when it
has none and the model can; with neither, the model is told facts cannot be looked up."""
import json

from paperdaemon import harnesses, loop, settings
from paperdaemon.models import adapters, cli as C, slots


def _lineup(text=None, search=None, name="L"):
    lu = settings.normalize_lineup({"name": name, "text": dict({"location": "http://127.0.0.1:9000"}, **(text or {})),
                                    "search": search or {}})
    s = settings.load()
    s["lineups"], s["lineup"] = [lu], name
    return s, name


def test_three_bases_with_what_each_model_can_do_by_default():
    weak, medium, strong = (harnesses.get(i) for i in ("weak-text", "default-text", "lean-default"))
    assert [h.name for h in (weak, medium, strong)] == ["Weak", "Medium", "Strong"]
    assert [h.id for h in harnesses.for_kind("text")][:3] == ["default-text", "lean-default", "weak-text"]
    for h in (weak, medium, strong):
        assert h.vision is True and h.image_generation is False
    assert (weak.web_search, medium.web_search, strong.web_search) == (False, False, True)
    assert weak.extends == "default-text" and not weak.lean and strong.lean
    assert set(weak.features["off"]) == {"draw", "posts", "web_picture", "adventure", "messages", "concord", "markup",
                                         "checkbox", "erase"}
    assert weak.max_output == 4096 and "short" in weak.brief_additions
    assert medium.notes.endswith("Tested with 27B class Qwen 3 models and Gemini 3.8 Flash.")


def test_the_model_searches_itself_only_when_the_lineup_has_no_search_and_it_can():
    own = {"harness": "lean-default"}
    s, n = _lineup(own)
    assert slots.searches_itself(s, settings.lineup(s, n)) is True
    assert slots.call_caps(s, settings.lineup(s, n))["web_search"] is True
    s, n = _lineup(own, {"kind": "local", "url": "http://127.0.0.1:8888"})
    assert slots.searches_itself(s, settings.lineup(s, n)) is False          # the lineup's search is used instead
    assert slots.call_caps(s, settings.lineup(s, n))["web_search"] is False
    s, n = _lineup({"harness": "default-text"})
    assert slots.searches_itself(s, settings.lineup(s, n)) is False          # Medium: the model cannot
    s, n = _lineup({"harness": "default-text", "overrides": {"web_search": True}})
    assert slots.searches_itself(s, settings.lineup(s, n)) is True           # the user ticked it
    s, n = _lineup(own)
    s["network"] = {"allowed": False}
    assert slots.searches_itself(s, settings.lineup(s, n)) is False          # the internet is off
    s, n = _lineup(own)
    assert loop.harness_values(s, n)["searches_itself"] is True


def test_the_command_line_turns_on_the_program_s_own_search_by_its_data():
    a = C.CommandLine("claude --model claude-opus-5-5")
    h = harnesses.get("lean-default")()
    args = a.request("sys", [{"role": "user", "text": "hi"}], caps={"vision": True, "web_search": True}, harness=h)[0]
    i = args.index("--tools")
    assert args[i + 1] == "WebSearch" and args[args.index("--allowedTools") + 1] == "WebSearch"
    args = a.request("sys", [{"role": "user", "text": "hi"}], caps={"vision": True}, harness=h)[0]
    assert args[args.index("--tools") + 1] == "" and "--allowedTools" not in args
    plain = C.CommandLine("some-other-program")                               # a program with no search in its data
    assert plain.request("sys", [{"role": "user", "text": "hi"}], caps={"web_search": True}, harness=h)[0] == []


def test_the_anthropic_api_gets_its_own_search_tool_only_when_the_model_searches_itself():
    a = adapters.AnthropicChat("https://api.anthropic.com/v1", "k", "claude-opus-5-5")
    tools = [{"name": "answer", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    body, _ = a.request("sys", [{"role": "user", "text": "hi"}], tools=tools, caps={"web_search": True})
    assert {"type": "web_search_20260209", "name": "web_search"} in body["tools"] and body["tools"][0]["name"] == "answer"
    body, _ = a.request("sys", [{"role": "user", "text": "hi"}], tools=tools, caps={})
    assert all(t.get("type") != "web_search_20260209" for t in body["tools"])


def test_the_brief_says_where_facts_come_from(monkeypatch):
    import paperdaemon.pipeline.host as H
    for name in ("LEAN", "_BRIEF", "_SCHEMA", "RUN"):
        monkeypatch.setattr(H, name, getattr(H, name))
    seen = {}
    for lean in (False, True):
        for features, own, where in (({}, False, "search"), ({"search": {"state": "off"}}, True, "own"),
                                     ({"search": {"state": "off"}}, False, "none")):
            H.LEAN, H._BRIEF, H._SCHEMA = lean, None, None
            H.RUN = dict(H.RUN, features=features, searches_itself=own)
            b = H.system_brief()
            assert (H.FACTS_LEAN if lean else H.FACTS)[where] in b and "<<" not in b
            seen[(lean, where)] = True
    assert len(seen) == 6
    assert "own web search" in H.FACTS["own"] and "cannot be looked up" in H.FACTS["none"]


def test_a_capability_is_a_yes_or_no_the_user_may_set():
    s, n = _lineup({"harness": "weak-text", "overrides": {"web_search": True, "image_generation": False}})
    assert not [e for e in settings.validate(s) if "web_search" in e or "image_generation" in e]
    caps = slots.capabilities("text", s, settings.lineup(s, n)["text"])
    assert caps["web_search"] == {"value": True, "source": "override"}
    assert caps["image_generation"]["value"] is False
    bad = _lineup({"harness": "weak-text", "overrides": {"web_search": "yes"}})[0]
    assert any("web_search must be" in e for e in settings.validate(bad))
    assert json.loads(json.dumps(harnesses.describe(harnesses.get("lean-default"))))["fields"]["web_search"] is True


def test_the_text_model_makes_the_pictures_when_the_image_tab_is_empty_and_it_can(monkeypatch):
    """A stand-in server, not a real model: the reply shapes are the ones gateways and Gemini's image models are
    documented to give (an `images` list, image parts in the content, inline data, a data URI in the words)."""
    import base64
    png = base64.b64encode(b"\x89PNG fake").decode()
    t = {"location": "https://api.example.test/v1", "api": "openai", "model": "an-image-model", "harness": "default-text",
         "overrides": {"image_generation": True}}
    s, n = _lineup(t)
    lu = settings.lineup(s, n)
    lu["image"]["location"] = ""
    assert slots.images_from_text(s, lu) is True
    lu["image"]["location"] = "http://127.0.0.1:8791"
    assert slots.images_from_text(s, lu) is False                    # the Image tab's model is used instead
    lu["image"]["location"] = ""
    lu["text"]["overrides"] = {}
    assert slots.images_from_text(s, lu) is False                    # the text model cannot
    lu["text"]["overrides"] = {"image_generation": True}
    s["lineup"] = n
    ad = adapters.for_slot("image", s)
    assert type(ad).__name__ == "TextModelImages" and ad.model == "an-image-model"
    body = ad.request("a red apple", 1024, 1024)
    assert body["modalities"] == ["image", "text"] and "a red apple" in body["messages"][0]["content"]
    for reply in ({"choices": [{"message": {"content": "", "images": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + png}}]}}]},
                  {"choices": [{"message": {"content": [{"type": "text", "text": "here"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png}}]}}]},
                  {"choices": [{"message": {"content": [{"inline_data": {"mime_type": "image/png", "data": png}}]}}]},
                  {"choices": [{"message": {"content": "Here it is: data:image/png;base64," + png}}]}):
        monkeypatch.setattr(adapters, "_request", lambda *a, **k: reply)
        assert ad.generate("a red apple", 1024, 1024) == b"\x89PNG fake"
    monkeypatch.setattr(adapters, "_request", lambda *a, **k: {"choices": [{"message": {"content": "I can't draw."}}]})
    try:
        ad.generate("a red apple", 1024, 1024)
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "without a picture" in str(ex)
    feats = __import__("paperdaemon.models.lineup", fromlist=["features"]).features(s, n)
    assert feats["image"]["state"] != "off"
    assert loop.harness_values(s, n)["image"]["name"] == "the text model itself"


def test_the_checklist_sentence_follows_whether_checkboxes_are_offered(monkeypatch):
    """Qwen3-VL 8B, asked to make a typed list a checklist, named no paragraphs and ruled the whole list erased; on
    Weak, checkboxes made of the user's own lines are off and the brief says to write the checklist anew."""
    import paperdaemon.pipeline.host as H
    for name in ("LEAN", "_BRIEF", "_SCHEMA", "RUN"):
        monkeypatch.setattr(H, name, getattr(H, name))
    for off, want in (({}, H.CHECKLIST[True]), ({"checkbox": {"state": "off"}}, H.CHECKLIST[False])):
        for lean in (False, True):
            H.LEAN, H._BRIEF, H._SCHEMA = lean, None, None
            H.RUN = dict(H.RUN, features=off)
            b = H.system_brief()
            assert want in b and "<<" not in b
    from paperdaemon.pipeline import features as F
    cat = F.Catalog()
    assert cat.step_feature()["checkbox"] == "checkbox" and cat.by_name["checkbox"].requires.features == ("write",)


def test_the_brief_names_what_is_not_offered(monkeypatch):
    """Qwen3-VL 8B, asked to underline with mark-ups off, wrote the sentence out again: the brief now names what is
    off, except search and checkboxes, which their own lines answer."""
    import paperdaemon.pipeline.host as H
    for name in ("LEAN", "_BRIEF", "_SCHEMA", "RUN"):
        monkeypatch.setattr(H, name, getattr(H, name))
    off = {n: {"state": "off"} for n in ("markup", "checkbox", "search", "draw")}
    for lean in (False, True):
        H.LEAN, H._BRIEF, H._SCHEMA = lean, None, None
        H.RUN = dict(H.RUN, features=off)
        b = H.system_brief()
        line = [x for x in b.splitlines() if x.startswith("NOT OFFERED HERE:")]
        assert len(line) == 1 and "underlining" in line[0] and "drawings" in line[0]
        assert "web" not in line[0] and "checkboxes" not in line[0] and b.rstrip().endswith(line[0])
    H._BRIEF, H.RUN = None, dict(H.RUN, features={})
    assert "NOT OFFERED HERE" not in H.system_brief()


def test_a_reply_that_writes_back_what_it_takes_off_is_refused(monkeypatch):
    """Qwen3-VL 8B, asked to underline a word with mark-ups off, erased the sentence and the request and wrote the
    sentence out again: the decision is refused with what to fix, and the same answer keeping the sentence is not."""
    from paperdaemon.pipeline.host import rulings as RU
    from paperdaemon.pipeline.host.job import JOB
    monkeypatch.setattr(JOB, "listing", {"para:1": {"text": "The harbor master rings a bell at noon every day.", "owner": "user"},
                                         "para:2": {"text": "Underline the word bell in the sentence above.", "owner": "user"}},
                        raising=False)
    monkeypatch.setattr(JOB, "new_refs", ["para:1", "para:2"], raising=False)
    line = "The harbor master rings a bell at noon every day. The word 'bell' is underlined in the sentence above."
    bad = RU.problems("answer", {"answers": ["para:1", "para:2"], "lines": [line],
                                 "rulings": [{"id": "para:1", "is": "request", "then": "erase"},
                                             {"id": "para:2", "is": "request", "then": "erase"}]})
    assert any(p.startswith("para:1 is ruled to come off, but the reply writes its words out again") for p in bad)
    assert not any(p.startswith("para:2 is ruled") for p in bad)
    ok = RU.problems("answer", {"answers": ["para:2"], "lines": ["Underlining isn't offered here."],
                                "rulings": [{"id": "para:1", "is": "note", "then": "keep"},
                                            {"id": "para:2", "is": "request", "then": "erase"}]})
    assert ok == []


def test_on_a_lineup_with_erasing_off_nothing_of_the_users_comes_off(monkeypatch):
    """The user's word (11-11), on Weak: nothing you wrote ever comes off; replies only add. Qwen3-VL 8B, asked which
    item doesn't belong, took the user's list off with the request. What this system wrote and the job makes stale still
    goes."""
    import paperdaemon.pipeline.host as H
    from paperdaemon.pipeline.host import rulings as RU
    from paperdaemon.pipeline.host.job import JOB
    monkeypatch.setattr(JOB, "listing", {"para:1": {"owner": "user"}, "para:2": {"owner": "user"},
                                         "picture:1": {"owner": "system"}}, raising=False)
    rulings = [{"id": "para:1", "is": "request", "then": "erase"}, {"id": "para:2", "is": "command", "then": "erase"},
               {"id": "picture:1", "is": "stale_work", "then": "erase"}]
    monkeypatch.setattr(H, "_off_features", lambda: set())
    assert [e["id"] for e in RU.erase_of(rulings)] == ["para:1", "para:2", "picture:1"]
    monkeypatch.setattr(H, "_off_features", lambda: {"erase"})
    assert [e["id"] for e in RU.erase_of(rulings)] == ["picture:1"]
    from paperdaemon import harnesses as HS
    assert "erase" in HS.get("weak-text").features["off"]


def test_a_checklist_run_together_on_one_line_is_a_line_per_item():
    from paperdaemon.pipeline.host.features import write as W
    assert W._mend_breaks(["- [ ] Milk - [ ] Eggs - [ ] Bread", "A plain line - with a dash.", "- [x] Done"]) == \
        ["- [ ] Milk", "- [ ] Eggs", "- [ ] Bread", "A plain line - with a dash.", "- [x] Done"]
