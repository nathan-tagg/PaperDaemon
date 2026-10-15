"""An image harness's workflows as the engine carries them out: the wording and settings of a named workflow,
a prompt sent as written when none is named, a workflow the harness lacks, and LoRAs per request."""
import json
import os

import pytest

from paperdaemon import card, harnesses, paths, settings
from paperdaemon.harnesses import COLORING_BOOK

COLORING = ("Black and white line art illustration of an owl on a branch, drawn for a young child to color in. "
            "Thick, clean, closed black outlines of even weight on a pure white background. Large "
            "simple shapes with big empty white areas inside them, a cute and friendly cartoon style. "
            "The whole drawing is shown complete, with plenty of empty white space around it and "
            "nothing cut off at the edges. No shading, no gray tones, no color, no hatching, no "
            "texture, no text.")


@pytest.fixture
def server(monkeypatch):
    """The image slot on a server nobody starts, with every request it would get recorded."""
    s = settings.load()
    settings.active(s)["image"].update(location="http://127.0.0.1:9", script="")
    settings.save(s)
    sent = {"bodies": [], "listed": []}

    def post(base, route, body):
        sent["bodies"].append((route, json.loads(json.dumps(body))))
        return b"\x89PNG fake"
    monkeypatch.setattr(card, "_sd_post", post)
    monkeypatch.setattr(card, "server_loras", lambda base: list(sent["listed"]))
    return sent


def _harness(name, d):
    d = dict({"server": "a test server", "models": ["a test model"]}, **d)
    with open(os.path.join(harnesses.user_folder(), "image", name), "w", encoding="utf-8") as f:
        json.dump(d, f)


def test_the_coloring_book_workflow_brings_its_wording_and_steps(server):
    item = card.generate({"prompt": "an owl on a branch", "workflow": COLORING_BOOK, "width": 832, "height": 1216})
    route, body = server["bodies"][-1]
    assert route == "txt2img" and body["prompt"] == COLORING and body["steps"] == 12
    assert item["workflow"] == COLORING_BOOK and item["workflow_missing"] is None and item["steps"] == 12
    assert "lora" not in body and item["loras"] == [] and item["loras_missing"] == []


def test_no_workflow_sends_the_prompt_as_written(server):
    text = "a sailboat on a calm lake at dawn, soft pink and gold light on the water"
    item = card.generate({"prompt": text})
    _route, body = server["bodies"][-1]
    assert body["prompt"] == text and body["steps"] == 4            # Klein's own default
    assert item["workflow"] is None and item["workflow_missing"] is None


def test_a_workflow_the_harness_lacks_does_not_fail_the_picture(server):
    item = card.generate({"prompt": "a dragon", "workflow": "characterTurnaround"})
    _route, body = server["bodies"][-1]
    assert body["prompt"] == "a dragon" and body["steps"] == 4
    assert item["workflow"] is None and item["workflow_missing"] == "characterTurnaround"


def test_the_models_and_the_users_steps_still_win(server):
    card.generate({"prompt": "an owl", "workflow": COLORING_BOOK, "steps": 30})
    assert server["bodies"][-1][1]["steps"] == 12                  # the model's own 30: clamped to Klein's 4..12
    card.generate({"prompt": "an owl", "workflow": COLORING_BOOK, "steps": 30, "user_numbers": [30]})
    assert server["bodies"][-1][1]["steps"] == 30                  # the user wrote 30


def test_the_same_workflow_on_z_image_uses_klein_wording_and_its_own_steps(server):
    s = settings.load()
    settings.active(s)["image"]["harness"] = "z-image-turbo"
    settings.save(s)
    item = card.generate({"prompt": "an owl on a branch", "workflow": COLORING_BOOK})
    body = server["bodies"][-1][1]
    assert body["prompt"].startswith("Black and white line art illustration of an owl on a branch") and body["steps"] == 8
    assert item["workflow"] == COLORING_BOOK


def test_a_workflows_lora_goes_with_that_request_only(server):
    _harness("ink.json", {"id": "ink", "extends": "flux.2-klein-9b", "workflows": {"inkWash": {
        "prompt": "An ink wash painting of {subject}.", "loras": [{"file": "styles/ink-wash.safetensors",
                                                                 "strength": 0.8}]}}})
    s = settings.load()
    settings.active(s)["image"]["harness"] = "ink"
    settings.save(s)
    server["listed"] = ["styles/ink-wash.safetensors", "other.safetensors"]
    item = card.generate({"prompt": "a heron", "workflow": "inkWash"})
    body = server["bodies"][-1][1]
    assert body["prompt"] == "An ink wash painting of a heron."
    assert body["lora"] == [{"path": "styles/ink-wash.safetensors", "multiplier": 0.8}]
    assert item["loras"] == ["styles/ink-wash.safetensors"] and item["loras_missing"] == []
    card.generate({"prompt": "a heron"})                            # no workflow: no adapter
    assert "lora" not in server["bodies"][-1][1]


def test_a_lora_is_found_by_its_file_name_in_a_subfolder(server):
    got, missing = card.lora_list([{"file": "ink-wash.safetensors", "strength": 1.0}],
                                  ["klein\\ink-wash.safetensors"])
    assert got == [{"path": "klein\\ink-wash.safetensors", "multiplier": 1.0}] and missing == []
    got, missing = card.lora_list([{"file": "ink-wash", "strength": 0.5}], ["klein/ink-wash.safetensors"])
    assert got == [{"path": "klein/ink-wash.safetensors", "multiplier": 0.5}]


def test_a_missing_lora_is_left_out_and_reported(server):
    _harness("ink.json", {"id": "ink", "extends": "flux.2-klein-9b", "workflows": {"inkWash": {
        "prompt": "An ink wash painting of {subject}.", "loras": [{"file": "ink-wash.safetensors", "strength": 0.8}]}}})
    s = settings.load()
    settings.active(s)["image"]["harness"] = "ink"
    settings.save(s)
    server["listed"] = ["something-else.safetensors"]
    item = card.generate({"prompt": "a heron", "workflow": "inkWash"})
    body = server["bodies"][-1][1]
    assert "lora" not in body and body["prompt"] == "An ink wash painting of a heron."   # made without it
    assert item["loras_missing"] == ["ink-wash.safetensors"] and item["workflow"] == "inkWash"


def test_a_reference_workflow_goes_through_an_edit(server):
    _harness("turn.json", {"id": "turn", "extends": "flux.2-klein-9b", "workflows": {"turnaround": {
        "prompt": "Four views of {subject}.", "steps": 8, "reference": True}}})
    s = settings.load()
    settings.active(s)["image"]["harness"] = "turn"
    settings.save(s)
    with pytest.raises(ValueError, match="starts from a picture"):
        card.generate({"prompt": "the knight", "workflow": "turnaround"})
    import base64
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    item = card.edit({"prompt": "the knight", "workflow": "turnaround", "mode": "ref",
                      "image": base64.b64encode(buf.getvalue()).decode()})
    route, body = server["bodies"][-1]
    assert route == "txt2img" and body["prompt"] == "Four views of the knight." and body["steps"] == 8
    assert body["extra_images"] and item["workflow"] == "turnaround"


def test_an_edit_the_harness_cannot_do_is_refused_before_the_server(server):
    s = settings.load()
    settings.active(s)["image"]["harness"] = "z-image-turbo"
    settings.save(s)
    with pytest.raises(card.NotReady, match="edit_reference|reference"):
        card.edit({"prompt": "make it night", "mode": "ref", "image": "AAAA"})
    assert server["bodies"] == []


def test_shipped_workflows_carry_no_lora():
    for h in harnesses.SHIPPED + (harnesses.DEFAULT["image"],):
        for wf in getattr(h, "workflows", {}).values():
            assert not wf.get("loras")


HOST = """
import json, sys
sys.path.insert(0, %(root)r)
import paperdaemon.pipeline  # noqa: F401
from paperdaemon.pipeline import host as H
sent = []
H._studio = lambda path, body=None, timeout=900: (sent.append((path, body)) or
    {"kind": "gen", "name": "x.png", "steps": 4, "seed": 1, "workflow": None,
     "workflow_missing": "characterTurnaround", "loras_missing": ["ink-wash.safetensors"]})

class R:
    def read(self):
        return b"png"
H._studio_open = lambda path, body=None, timeout=900: R()
import os
os.makedirs(H.QUEUE, exist_ok=True)
H.JOB.update(paras=["Draw a dragon, 30 steps."], mark_words={}, sprompt="",
             steps=[{"do": "image", "what": "a dragon", "steps": 30, "quote": "30 steps"}])
H._generate_png("a dragon", 512, workflow="characterTurnaround", steps=30)
print(json.dumps(sent[-1][1]))
"""


def test_the_host_asks_by_name_and_logs_what_the_image_model_lacked(tmp_path):
    import subprocess
    import sys as _sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"),
               PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([_sys.executable, "-c", HOST % {"root": root}], env=env, capture_output=True, text=True,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    lines = out.stdout.strip().splitlines()
    body = json.loads(lines[-1])
    # the subject alone, by workflow name; the user's own 30 steps (quoted) go along as the user's
    assert body["prompt"] == "a dragon" and body["workflow"] == "characterTurnaround"
    assert body["steps"] == 30 and 30 in body["user_numbers"]
    log = "\n".join(lines[:-1])
    assert "no 'characterTurnaround' workflow: the subject went as a plain prompt" in log
    assert "LoRA 'ink-wash.safetensors' is not in the image server's LoRA folder" in log
