"""The Test tab: the models, the page cases and the direct tests, as one table of rows with a figure and a write-up."""
import json
import os

from paperdaemon import paths, settings
from paperdaemon import benchmark as B
from paperdaemon.benchmark import probes


def test_words_are_counted_once_each_whatever_the_case_or_punctuation():
    assert probes.word_score("The cat, the CAT sat.", ["the", "cat", "sat", "on", "the", "mat"]) == (4, 6)
    assert probes.word_score("", ["a"]) == (0, 1)


def test_the_cases_become_rows_with_their_answer(fresh, monkeypatch):
    cases = [{"id": "typed-question", "result": "pass", "seconds": 20.5, "notes": [],
              "note": "write the question. Wrote: Mars has two moons, Phobos and Deimos."},
             {"id": "draw", "result": "fail", "seconds": 61.0, "notes": ["the page gained no drawing"], "note": ""},
             {"id": "coloring-page", "result": "pass", "seconds": 30.0, "notes": [], "note": ""}]
    hw = probes._entry("handwriting", "Read handwriting", "partly", "70% of words", "")
    models = [probes._entry("model-text", "Text model", "pass", "Answers"),
              probes._entry("model-image", "Image model", "off", "No image model")]
    monkeypatch.setitem(B._run, "cases", cases)
    monkeypatch.setitem(B._run, "models", models)
    monkeypatch.setitem(B._run, "image", False)                              # a lineup without an image model
    monkeypatch.setitem(B._run, "probes", [hw, probes._entry("weather", "Weather", "pass", "50°F", "")])
    monkeypatch.setitem(B._run, "running", False)
    monkeypatch.setitem(B._run, "finished", 1)
    monkeypatch.setitem(B._run, "cancel", None)
    rows = B.rows()
    by = {r["id"]: r for r in rows}
    assert [r["id"] for r in rows][:5] == ["model-text", "model-image", "answer", "draw", "handwriting"]
    assert by["answer"]["state"] == "pass" and by["answer"]["detail"] == "Mars has two moons, Phobos and Deimos."
    assert by["draw"]["state"] == "fail" and by["draw"]["metric"] == "Failed after 61.0 s"
    assert by["picture"]["state"] == "off" and by["picture"]["metric"] == "No image model"
    assert rows[-1]["id"] == "weather" and not [r for r in rows if r["state"] == "wait"]


def test_search_is_always_listed_and_says_when_it_is_not_set_up(fresh):
    got = probes.web_search(settings.load())
    assert got["name"] == "Search the web" and got["state"] == "off" and got["metric"] == "Not set up"


def test_social_reports_each_site_and_partly_when_one_fails(fresh, monkeypatch):
    from paperdaemon.pipeline.charts import reddit, social
    monkeypatch.setattr(reddit, "posts", lambda *a, **k: [{"title": "a post"}])
    monkeypatch.setattr(social, "fetch", lambda src, **k: ([{"title": "x"}], None) if src == "hn" else (None, "down"))
    s = settings.load()
    got = probes.social(s)                          # every site, always: Reddit and Hacker News answer, the rest do not
    assert got["state"] == "partly" and got["metric"].startswith("Reddit ") and "Bluesky failed" in got["metric"]
    s["network"]["allowed"] = False
    assert probes.social(s)["state"] == "off"


def test_handwriting_scores_the_model_reading_against_the_transcription(fresh, monkeypatch):
    from paperdaemon import card
    from paperdaemon.models import adapters, slots
    folder = paths.content_path(*probes.HANDWRITING)
    samples = json.load(open(os.path.join(folder, "samples.json"), encoding="utf-8"))["samples"]
    assert len(samples) == 12 and {x["region"] for x in samples} == {"Africa", "Asia", "Europe", "North America"}

    class Reader:                                   # reads every page perfectly but the last word
        def chat(self, system, messages, **kw):
            name = [x for x in samples if True][self.n]["words"]
            self.n += 1
            return {"text": " ".join(name[:-1])}
    reader = Reader()
    reader.n = 0
    monkeypatch.setattr(adapters, "for_slot", lambda role, s=None: reader)
    monkeypatch.setattr(slots, "caps", lambda role, s=None, slot=None: {"vision": True})
    monkeypatch.setattr(slots, "harness", lambda role, s=None, slot=None: None)

    class Call:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(card, "call", lambda role: Call())
    got = probes.handwriting(settings.load())
    total = sum(len(x["words"]) for x in samples)
    assert got["state"] == "pass" and got["metric"].startswith("%d%% of words" % round(100 * (total - 12) / total))
    assert "12 pages" in got["detail"]
