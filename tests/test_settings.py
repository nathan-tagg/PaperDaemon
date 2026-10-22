import copy
import json
import os

import pytest

from paperdaemon import paths, settings, vault

# what PaperDaemon itself ships, read before the tests' fixture puts its own lineups in
REAL_SHIPPED = copy.deepcopy(settings.SHIPPED_LINEUPS)
REAL_DEFAULT = settings.DEFAULT_LINEUP


def test_first_start_uses_defaults():
    s = settings.load()
    assert "trigger_tag" not in s.get("tablet", {})          # each lineup has its own tags, none at first
    assert all(lu["tags"] == [] for lu in s["lineups"])
    assert "mute_tag" not in s.get("tablet", {}) and "sprompt_tag" not in s.get("tablet", {})   # fixed names, not settings
    assert s["tags"]["inbox"] == "inbox"
    assert s["location"]["lat"] is None               # nothing is built in
    assert not settings.exists()


def test_one_blank_lineup_ships():
    assert [lu["name"] for lu in REAL_SHIPPED] == ["Lineup 1"] and REAL_DEFAULT == "Lineup 1"
    for role in ("text", "image"):
        slot = REAL_SHIPPED[0][role]
        assert slot["location"] == "" and slot["script"] == "" and slot["harness"] == "auto"


def test_ports_avoid_other_local_model_software():
    used = {11434, 1234, 7860, 8080, 8767, 8888}
    assert not {settings.API_PORT, settings.TEXT_PORT, settings.IMAGE_PORT} & used
    assert len({settings.API_PORT, settings.TEXT_PORT, settings.IMAGE_PORT}) == 3


def test_older_file_keeps_its_values_and_gains_new_defaults():
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump({"tablet": {"trigger_tag": "Answer"}, "models": {"text": {"url": "http://x"}}}, f)
    s = settings.load()
    assert "trigger_tag" not in s["tablet"] and "inbox" not in s["tablet"]
    # the old tag goes to the lineup that was in use then (a tag belongs to one lineup)
    assert [lu["tags"] for lu in s["lineups"]] == [[{"name": "Answer", "prompt": ""}], []]
    assert "models" not in s and len(s["lineups"]) == 2


def test_a_saved_lineup_gains_missing_slot_fields():
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump({"lineups": [{"name": "Mine", "text": {"location": "http://127.0.0.1:9000"}}], "lineup": "Mine"}, f)
    lu = settings.active()
    assert lu["text"]["location"] == "http://127.0.0.1:9000"
    assert lu["text"]["harness"] == "auto" and lu["text"]["api"] == "openai"
    assert lu["image"]["location"] == "" and lu["image"]["api"] == "sdapi"


def test_the_inbox_is_a_tag_and_the_old_inbox_paths_go():
    import json
    from paperdaemon import paths
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump({"tablet": {"inbox": "Projects/Pictures inbox"}, "false_mirror": {"inbox": "FM inbox", "faces": "own"}}, f)
    s = settings.load()
    assert "inbox" not in s["tablet"] and "inbox" not in s["false_mirror"] and s["false_mirror"]["faces"] == "own"
    assert settings.inbox_tag(s) == "inbox"
    s["tags"]["inbox"] = "Outbox"
    settings.save(s)
    assert settings.inbox_tag(settings.load()) == "Outbox"
    s["tags"]["inbox"] = "ignore"
    assert any("must all be different" in e for e in settings.validate(s))


def _first(s):
    return s["lineups"][0]


@pytest.mark.parametrize("edit,message", [
    (lambda s: _first(s).update(tags=[{"name": "Ignore", "prompt": ""}]), "cannot also be the ignore tag"),
    (lambda s: _first(s).update(tags=[{"name": "SPROMPT", "prompt": ""}]), "cannot also be the standing instructions tag"),
    (lambda s: s["server"].update(listen=["10.0.0.2"]), "must include 127.0.0.1"),
    (lambda s: s["server"].update(port=80), "1024 to 65535"),
    (lambda s: s["location"].update(lat=123), "location.lat"),
    (lambda s: _first(s)["text"].update(location="ftp://x"), "must start with http"),
    (lambda s: _first(s)["text"].update(api="sdapi"), "api is one of"),
    (lambda s: _first(s)["image"].update(harness="qwen3.6-27b"), "is not a image harness"),
    (lambda s: _first(s)["text"].update(overrides={"steps": 4}), "not a capability of a text model"),
    (lambda s: _first(s)["image"].update(overrides={"steps": 0}), "from 1 to 150"),
    (lambda s: s.update(lineups=[]), "at least one lineup"),
    (lambda s: s["lineups"].append(dict(_first(s))), "cannot share a name"),
    (lambda s: _first(s).update(name="a/b"), "without slashes"),
])
def test_invalid_settings_are_refused_whole(edit, message):
    s = settings.load()
    edit(s)
    with pytest.raises(ValueError, match=message):
        settings.save(s)
    assert not os.path.exists(paths.settings_file())


def test_a_remote_slot_needs_no_script():
    s = settings.load()
    _first(s)["text"].update(location="https://api.example.com", script="", api="anthropic")
    assert settings.save(s)["lineups"][0]["text"]["api"] == "anthropic"


def test_a_forced_lineup_is_used_without_being_saved():
    s = settings.load()
    settings.force("Qwen 3.6 + Klein")
    try:
        assert settings.active(s)["name"] == "Qwen 3.6 + Klein"
        assert settings.load()["lineup"] == "Qwen 3.8 + Klein"
    finally:
        settings.force(None)
    assert settings.active(s)["name"] == "Qwen 3.8 + Klein"


def test_save_is_atomic_and_leaves_no_temp_file():
    settings.save(settings.load())
    assert os.path.exists(paths.settings_file())
    assert not os.path.exists(paths.settings_file() + ".tmp")


def test_keys_never_reach_the_settings_file():
    vault.put("key:text", "sk-test-not-a-real-key-000000")
    settings.save(settings.load())
    with open(paths.settings_file(), encoding="utf-8") as f:
        assert "sk-test" not in f.read()
    assert vault.get("key:text") == "sk-test-not-a-real-key-000000"


def test_a_file_from_before_the_rename_upgrades_on_load():
    # slots once named their harness "profile", and an image slot could override coloring_steps
    old = {"lineups": [{"name": "Mine",
                        "text": {"location": "http://127.0.0.1:8790", "profile": "qwen3.8-27b"},
                        "image": {"location": "http://127.0.0.1:8791", "profile": "flux.2-klein-9b",
                                  "overrides": {"coloring_steps": 10, "steps": 6}}}],
           "lineup": "Mine"}
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump(old, f)
    lu = settings.active()
    assert lu["text"]["harness"] == "qwen3.8-27b" and "profile" not in lu["text"]
    assert lu["image"]["harness"] == "flux.2-klein-9b" and lu["image"]["overrides"] == {"steps": 6}
    saved = settings.save(settings.load())                 # valid as it is, and written in the new shape
    with open(paths.settings_file(), encoding="utf-8") as f:
        text = f.read()
    assert '"profile"' not in text and "coloring_steps" not in text
    assert saved["lineups"][0]["text"]["harness"] == "qwen3.8-27b"


def test_a_slot_naming_both_keeps_its_harness():
    lu = settings.normalize_lineup({"name": "X", "text": {"profile": "qwen3.6-27b", "harness": "qwen3.8-27b"}})
    assert lu["text"]["harness"] == "qwen3.8-27b" and "profile" not in lu["text"]


def test_the_ignore_and_sprompt_settings_are_dropped_on_load():
    with open(paths.settings_file(), "w", encoding="utf-8") as f:
        json.dump({"tablet": {"trigger_tag": "Answer", "mute_tag": "quiet", "sprompt_tag": "rules"}}, f)
    s = settings.load()
    assert "trigger_tag" not in s["tablet"] and s["lineups"][0]["tags"] == [{"name": "Answer", "prompt": ""}]
    assert "mute_tag" not in s["tablet"] and "sprompt_tag" not in s["tablet"]
    settings.save(s)
    with open(paths.settings_file(), encoding="utf-8") as f:
        assert "mute_tag" not in f.read()
    assert settings.FIXED_TAGS == ("ignore", "sprompt", "inbox")


def test_a_lineup_draws_its_pages_on_the_card_unless_it_says_the_processor():
    from paperdaemon import settings
    assert settings.normalize_lineup({"name": "a"})["render"] == "card"
    assert settings.normalize_lineup({"name": "a", "render": "cpu"})["render"] == "cpu"
    assert settings.normalize_lineup({"name": "a", "render": "nonsense"})["render"] == "card"


def test_a_processor_lineup_never_asks_the_card():
    import numpy as np
    from paperdaemon.pipeline.page import gpu
    asked = []
    real = gpu._ask
    gpu._ask = lambda job, wait=True: asked.append(job)
    try:
        gpu.processor(True)
        assert gpu.paint(np.zeros((4, 4, 3), np.uint8), None) is None
        gpu.warm()
        assert asked == []
    finally:
        gpu.processor(False)
        gpu._ask = real
