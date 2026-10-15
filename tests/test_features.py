"""The feature list: requirements hard and optional, chains of reasons, cycles refused, the run file, the
API, a refused step of a feature that is off, and a catalog the engine reads without loading the host."""
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from paperdaemon import loop, server, settings
from paperdaemon.pipeline import features as F

ALL_ON = {"text": {"vision": True, "forced_tool": True}, "image": ["generate", "edit_reference"],
          "workflows": ["childrensColoringBook"], "search": True, "content": ["characters", "chess engine"],
          "settings": ["location"], "off": {}}


def test_everything_is_on_when_everything_is_there():
    got = F.resolve(F.Catalog(), ALL_ON)
    assert {n for n, st in got.items() if st["state"] != "on"} == set()


def test_no_image_slot_turns_the_picture_features_off_with_reasons():
    got = F.resolve(F.Catalog(), dict(ALL_ON, image=None, workflows=[]))
    for n in ("image", "coloring", "picture_edit"):
        assert got[n]["state"] == "off" and got[n]["because"]
    assert got["adventure"]["state"] == "degraded"               # it plays without pictures


def test_a_missing_workflow_degrades_coloring():
    got = F.resolve(F.Catalog(), dict(ALL_ON, workflows=[]))
    assert got["coloring"] == {"state": "degraded", "because": ["the image model has no childrensColoringBook workflow"]}


def test_a_chain_of_three_names_every_link():
    got = F.resolve(F.Catalog(), dict(ALL_ON, search=False))
    assert got["search"]["because"] == ["no search provider is configured"]
    assert got["web_picture"]["because"] == ["search is off because no search provider is configured"]


def test_the_user_and_the_harness_switch_features_off():
    got = F.resolve(F.Catalog(), dict(ALL_ON, off={"posts": "it is switched off in the settings"}))
    assert got["posts"] == {"state": "off", "because": ["it is switched off in the settings"]}


def test_a_cycle_is_refused_naming_its_features():
    a = type("A", (F.Feature,), dict(name="a", requires=F.Requires(features=("b",))))
    b = type("B", (F.Feature,), dict(name="b", requires=F.Requires(features=("a",))))
    with pytest.raises(F.CatalogError, match="a -> b -> a|b -> a -> b"):
        F.Catalog((a, b))
    with pytest.raises(F.CatalogError, match="not a feature"):
        F.Catalog((type("C", (F.Feature,), dict(name="c", requires=F.Requires(features=("z",)))),))


def test_the_catalog_loads_nothing_heavy():
    code = ("import sys; from paperdaemon.pipeline import features; features.Catalog(); "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in ('numpy', 'PIL', 'cv2', 'numba', 'rmscene') "
            "or m.startswith('paperdaemon.pipeline.host')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "[]", out.stderr[-500:]


def test_the_run_file_and_the_api_carry_the_features(fresh):
    settings.save(settings.load())               # a fresh lineup has no search provider
    with open(loop.environment(settings.load())["RM_RUN"], encoding="utf-8") as f:
        run = json.load(f)
    assert run["features"]["search"]["state"] == "off" and "location" in run["settings"]
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    got = c.get("/api/v1/lineups/Qwen 3.8 + Klein/features").json()["features"]
    assert got["web_picture"]["because"] == ["search is off because no search provider is configured"]
    assert c.get("/api/v1/lineups/nobody/features").status_code == 404


def test_the_host_refuses_a_step_of_a_feature_that_is_off(tmp_path):
    run = tmp_path / "lineup.json"
    run.write_text(json.dumps({"features": {"image": {"state": "off", "because": ["the lineup has no image model"]}}}),
                   encoding="utf-8")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, %r); from paperdaemon.pipeline import host as H; "
            "print(H._off_steps([{'do': 'image', 'what': 'a fox'}])); print(H._off_steps([{'do': 'write', 'what': 'x'}]))" % root)
    env = dict(os.environ, RM_RUN=str(run), RM_STATE=str(tmp_path), RM_MIRROR=str(tmp_path), RM_CACHE=str(tmp_path),
               PAPERDAEMON_HOME=str(tmp_path), PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    lines = out.stdout.strip().splitlines()
    assert lines[-2].startswith("the image step is off: image is off because the lineup has no image model"), out.stderr[-800:]
    assert lines[-1] == "None"


def test_what_the_harness_declares_turns_kinds_off_and_abilities_on(fresh):
    from paperdaemon import harnesses
    from paperdaemon.models import lineup
    folder = os.path.join(harnesses.user_folder(), "llm")
    with open(os.path.join(folder, "painter.py"), "w", encoding="utf-8") as f:
        f.write("from paperdaemon import harnesses\n\n\n"
                "class Painter(harnesses.DEFAULT['text']):\n"
                "    id = 'painter'\n    server = 'An API'\n    models = ['A model that paints']\n"
                "    kinds = {'write', 'erase', 'image', 'search'}\n    provides = {'pictures', 'search'}\n")
    s = settings.load()
    lu = settings.active(s)
    lu["text"]["harness"] = "painter"
    lu["image"]["location"] = ""
    settings.save(s)
    got = lineup.features(settings.load())
    assert got["draw"]["state"] == "off" and got["draw"]["because"][0].startswith("this harness does not do")
    assert got["image"]["state"] == "on" and "the model does it itself" in got["image"]["because"]
    assert got["search"]["state"] == "on" and "the model does it itself" in got["search"]["because"]
    assert got["write"]["state"] == "on"
