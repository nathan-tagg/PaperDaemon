"""Tags: every lineup's tags are live at once, each with its prompt, and each belongs to one lineup only; the ignore
and standing-instructions tags are PaperDaemon's own (Settings), and no lineup may watch for either."""
import json

from paperdaemon import ledger, loop, paths, settings


def test_a_new_lineup_watches_nothing():
    assert settings.normalize_lineup({"name": "x"})["tags"] == []


def test_tags_are_checked():
    ok = [{"name": "Ask", "prompt": ""}, {"name": "plain", "prompt": "Simple words."}]
    assert settings.check_tags(ok, "L") == []
    assert settings.check_tags([{"name": "", "prompt": "x"}], "L")             # a tag needs its name
    assert settings.check_tags(ok + [{"name": "ask", "prompt": ""}], "L")       # no two the same


def test_tags_are_unique_across_paperdaemon():
    s = settings.load()
    s["lineups"][0]["tags"] = [{"name": "Ask", "prompt": ""}]
    s["lineups"][1]["tags"] = [{"name": "ask", "prompt": ""}]
    assert any("already" in e for e in settings.validate(s))
    s["lineups"][1]["tags"] = [{"name": "sprompt", "prompt": ""}]
    assert any("standing instructions" in e for e in settings.validate(s))
    s["lineups"][1]["tags"] = [{"name": "Other", "prompt": ""}]
    assert settings.validate(s) == []
    assert settings.lineup_of_tag(s, "OTHER")["name"] == s["lineups"][1]["name"]
    assert settings.lineup_name_for(s, "Ask: draw a cat") == s["lineups"][0]["name"]
    assert settings.lineup_name_for(s, "Askew") is None


def test_an_earlier_lineups_tags_become_the_list_and_ignore_and_sprompt_go_global():
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump({"lineups": [{"name": "A", "tags": {"watch": "Ask", "ignore": "quiet", "sprompt": "sprompt",
                                                       "custom": [{"name": "plain", "prompt": "Simple words."}]}}],
                   "lineup": "A"}, f)
    s = settings.load()
    assert s["lineups"][0]["tags"] == [{"name": "Ask", "prompt": ""}, {"name": "plain", "prompt": "Simple words."}]
    assert settings.fixed_tags(s) == ("quiet", "sprompt")


def test_no_tag_anywhere_is_no_reason_to_stop(monkeypatch):
    from paperdaemon.remarkable import auth
    monkeypatch.setattr(auth, "describe", lambda: {"set": True})
    assert loop.preflight(settings.load()) is None              # the daemon runs and finds nothing to work


def test_the_longest_watched_tag_wins(monkeypatch):
    monkeypatch.setattr(ledger, "TRIGGERS", ["qwen", "qwen fast"])
    assert ledger.trigger_of("Qwen fast: draw a cat") == "qwen fast"
    assert ledger.parse_directive("Qwen fast: draw a cat") == "draw a cat"
    assert ledger.trigger_of("qwen") == "qwen" and ledger.trigger_of("qwenny") is None


def test_the_engine_hands_every_lineups_tags_to_the_halves():
    s = settings.load()
    s["lineups"][0]["tags"] = [{"name": "Ask", "prompt": ""}]
    s["lineups"][1]["tags"] = [{"name": "Draw", "prompt": "Draw it."}]
    settings.save(s)
    env = loop.environment(settings.load())
    assert json.loads(env["RM_TRIGGERS"]) == ["Ask", "Draw"]
    run = json.load(open(env["RM_RUN"], encoding="utf-8"))
    assert run["tag_lineup"] == {"ask": s["lineups"][0]["name"], "draw": s["lineups"][1]["name"]}
    assert run["lineups"][s["lineups"][1]["name"]]["tags"] == [{"name": "Draw", "prompt": "Draw it."}]
    assert run["settings"]["tags"] == {"ignore": "ignore", "sprompt": "sprompt"}
