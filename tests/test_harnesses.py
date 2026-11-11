import json
import os

import pytest

from paperdaemon import harnesses, paths, settings
from paperdaemon.models import slots
from paperdaemon.harnesses import COLORING_BOOK

DefaultText, DefaultImage = harnesses.DEFAULT["text"], harnesses.DEFAULT["image"]
Flux2Klein9B, ZImageTurbo = harnesses.get("flux.2-klein-9b"), harnesses.get("z-image-turbo")
LeanDefault = harnesses.get("lean-default")


@pytest.mark.parametrize("kind,hint,want", [
    ("text", "Qwen3.6-27B", DefaultText),
    ("text", "qwen3.6-27b-Q8_0.gguf", DefaultText),
    ("text", "Qwen_Qwen3.6-27B-Instruct", DefaultText),
    ("text", "Qwen3.6 27B", DefaultText),
    ("text", "qwen3.8-27b-q4km.gguf", DefaultText),
    ("text", "Qwen3.8-27B-Q5_K_S.gguf", DefaultText),
    ("text", "Qwen3.8 27B", DefaultText),
    ("text", "Qwen3.8-27B-Base-Q8_0.gguf", DefaultText),     # pretrained, not instruction-tuned
    ("text", "qwen3-14b-q4_k_m.gguf", DefaultText),
    ("text", "Qwen3.6-27B-Base-Q8_0.gguf", DefaultText),
    ("text", "claude-opus-5-5", LeanDefault),              # the harnesses of 0.2.39 to 0.2.50 for these are Lean Default
    ("text", "claude-sonnet-5-5", LeanDefault),
    ("text", "haiku", LeanDefault),
    ("text", "claude-sonnet-4-6", DefaultText),
    ("image", "flux-2-klein-9b-Q8_0.gguf", Flux2Klein9B),
    ("image", "FLUX.2-klein-9B-BF16.gguf", Flux2Klein9B),
    ("image", "flux-2-klein-base-9b.gguf", DefaultImage),     # undistilled: different parameters
    ("image", "z_image_turbo_bf16.safetensors", ZImageTurbo),
    ("image", "Tongyi-MAI/Z-Image-Turbo", ZImageTurbo),
    ("image", "fuzz-imagery-v2.safetensors", DefaultImage),
    ("image", "Qwen3.6-27B", DefaultImage),                   # a text harness never fits an image slot
])
def test_a_slot_saved_as_automatic_keeps_the_harness_it_ran_on(kind, hint, want):
    """PaperDaemon does not choose a harness ("ZERO inference"). Versions to 0.2.50 did, from the model's name, when a
    slot said "automatic": such a slot is given, once, as its settings are read, the harness it was running on."""
    assert harnesses.was_automatic(kind, model=hint) == want.id
    old = {"location": "http://127.0.0.1:9000", "model": hint, "harness": "auto"}
    assert settings.upgrade_slot(old, kind)["harness"] == want.id
    assert settings.upgrade_slot(dict(old, harness="default-" + kind), kind)["harness"] == "default-" + kind   # a pick stands


def test_the_start_script_s_model_file_counted_after_the_model_s_name():
    assert harnesses.was_automatic("image", launch=r'sd-server.exe --diffusion-model "C:\m\flux-2-klein-9b-Q8_0.gguf" '
                                                   r'--vae C:\m\ae.safetensors') == "flux.2-klein-9b"
    assert harnesses.was_automatic("image", model="z_image_turbo.gguf",
                                   launch=r"sd-server.exe --diffusion-model C:\m\flux-2-klein-9b-Q8_0.gguf") == "z-image-turbo"
    script = 'set "MODEL=%MODELS%\\flux-2-klein-9b-Q8_0.gguf"\r\n"%SERVER%" --diffusion-model "%MODEL%"\r\n'
    assert harnesses.was_automatic("image", launch=script) == "flux.2-klein-9b"       # a batch file's variable


def test_nothing_chooses_a_harness_any_more():
    """The slot's harness is the one it names; one that is gone, or none, is the default of its kind. No model name,
    reported model or start script changes that."""
    assert not hasattr(harnesses, "guess")
    for model in ("lean-default", "claude-opus-5-5", "anything"):
        m = dict(settings.slot_defaults("text"), location="http://127.0.0.1:9000", model=model)
        assert m["harness"] == "default-text" and slots.pick("text", None, m)[0] is DefaultText
        assert slots.pick("text", None, dict(m, harness="lean-default"))[0] is LeanDefault
        assert slots.pick("text", None, dict(m, harness="a-file-since-removed"))[0] is DefaultText
        assert slots.pick("text", None, dict(m, harness="auto"))[0] is DefaultText       # (unread by any upgrade: still no guess)
    slots.report_models("text", ["lean-default"])
    try:
        assert slots.pick("text", None, dict(settings.slot_defaults("text"), location="http://127.0.0.1:9000"))[0] is DefaultText
    finally:
        slots.report_models("text", [])
    assert [h.name for h in harnesses.for_kind("text")][:3] == ["Medium", "Strong", "Weak"]
    assert harnesses.for_kind("image")[0].name == "Default"
    for gone in ("claude-opus-5.5", "claude-sonnet-5.5", "claude-haiku-5.5"):
        assert harnesses.get(gone) is None
        assert settings.upgrade_slot({"location": "x", "harness": gone}, "text")["harness"] == "lean-default"


def test_model_harnesses_override_only_what_differs():
    # the default carries everything; a model harness names only its differences
    assert DefaultText.vision is True and DefaultText.forced_tool is True
    assert LeanDefault.vision and LeanDefault.forced_tool and LeanDefault.extends == "default-text"
    assert set(json.load(open(os.path.join(os.path.dirname(harnesses.__file__), "shipped", "lean-default.json"),
                              encoding="utf-8"))) == {"id", "name", "server", "models", "extends", "notes", "lean", "web_search"}


def test_the_default_says_what_it_was_designed_for_and_the_harnesses_folded_into_it_name_it():
    """'fold them in, but in their header state that they were designed for qwen 3 models running in llama.cpp'."""
    assert DefaultText.notes.startswith("Built for Qwen 3 models running in llama.cpp.")
    assert DefaultText.server.startswith("llama.cpp") and DefaultText.models[:2] == ("Qwen 3.6 27B", "Qwen 3.8 27B")
    for gone in ("qwen3.6-27b", "qwen3.8-27b"):
        assert harnesses.get(gone) is None
        assert settings.upgrade_slot({"location": "http://127.0.0.1:8080", "harness": gone}, "text")["harness"] == "default-text"
    _user_harness("small.json", {"extends": "qwen3.6-27b", "max_output": 16384})    # a user's file written for one of them
    assert harnesses.user_errors() == [] and harnesses.get("small").extends == "default-text"


def test_no_harness_sets_thinking_or_context():
    for h in harnesses.BUILT_IN:
        assert not hasattr(h, "thinking") and not hasattr(h, "context"), h.id
    assert LeanDefault().tune({}, {}) == {}


# the coloring prompt as the pipeline host wrote it before the image harness owned it, word for word
HOST_COLORING_PROMPT = ("Black and white line art illustration of {what}, drawn for a young child to color in. "
                        "Thick, clean, closed black outlines of even weight on a pure white background. Large "
                        "simple shapes with big empty white areas inside them, a cute and friendly cartoon style. "
                        "The whole drawing is shown complete, with plenty of empty white space around it and "
                        "nothing cut off at the edges. No shading, no gray tones, no color, no hatching, no "
                        "texture, no text.")


def test_the_coloring_book_workflow_keeps_its_wording_and_klein_its_12_steps():
    prompt, settings_, missing = Flux2Klein9B.apply("an owl on a branch", COLORING_BOOK)
    assert prompt == HOST_COLORING_PROMPT.format(what="an owl on a branch") and missing is None
    assert settings_ == {"steps": 12}
    assert Flux2Klein9B.steps == 4 and Flux2Klein9B.steps_range == (4, 12)
    # the default image harness words it the same and leaves the steps to the model's default
    assert DefaultImage.apply("an owl", COLORING_BOOK) == (HOST_COLORING_PROMPT.format(what="an owl"), {}, None)


def test_a_workflow_name_is_shared_and_each_harness_carries_it_out_with_its_own_settings():
    z, zs, _ = ZImageTurbo.apply("a fox", COLORING_BOOK)
    k, ks, _ = Flux2Klein9B.apply("a fox", COLORING_BOOK)
    assert z.startswith("Black and white line art illustration of a fox") and zs == {}          # Klein's wording, its own steps
    assert k.startswith("Black and white line art illustration of a fox") and ks == {"steps": 12}
    for h in (DefaultImage, Flux2Klein9B, ZImageTurbo):
        assert COLORING_BOOK in h.offer()["workflows"]


def test_no_workflow_sends_the_prompt_exactly_as_written():
    text = "a sailboat on a calm lake at dawn, soft pink and gold light, painterly"
    assert Flux2Klein9B.apply(text) == (text, {}, None)
    assert Flux2Klein9B.apply(text, "") == (text, {}, None)


def test_a_workflow_the_harness_lacks_sends_the_plain_prompt_and_says_so():
    assert ZImageTurbo.apply("a dragon", "characterTurnaround") == ("a dragon", {}, "characterTurnaround")


def test_image_harnesses_advertise_their_abilities():
    assert Flux2Klein9B.can("edit_reference") and not ZImageTurbo.can("edit_reference")
    offer = Flux2Klein9B.offer()
    assert offer["name"] == "stable-diffusion.cpp - FLUX.2 Klein 9B" and "edit_reference" in offer["abilities"]
    assert offer["workflows"][COLORING_BOOK]["reference"] is False and offer["steps_range"] == [4, 12]


def test_every_field_has_a_value_and_a_rule():
    from paperdaemon.harnesses import schema as rules
    for p in (DefaultText, DefaultImage):
        for f in p.FIELDS:
            assert hasattr(p, f) and f in rules.RULES
            assert rules.check(f, p.fields()[f]) is None


def _user_harness(name, d, declared=True):
    """A harness file; `declared` adds what every file says about itself (its server and models)."""
    if declared:
        d = dict({"server": "a test server", "models": ["a test model"]}, **d)
    image = d.get("kind") == "image" or str(d.get("extends") or "") in ("flux.2-klein-9b", "z-image-turbo", "default-image")
    folder = os.path.join(paths.sub("harnesses"), "image" if image else "llm")
    os.makedirs(os.path.dirname(os.path.join(folder, name)), exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        json.dump(d, f)


def test_user_harnesses_override_what_they_name():
    _user_harness("small.json", {"name": "Qwen 3.6, small context", "extends": "lean-default", "max_output": 16384,
                                 "brief_additions": "Answer in one sentence."})
    _user_harness("textonly.json", {"id": "text-only", "kind": "text", "vision": False})
    _user_harness("chain.json", {"id": "chain", "extends": "small", "max_output": 2048})
    p = harnesses.get("small")
    assert p.name == "Qwen 3.6, small context" and p.source == "user" and p.extends == "lean-default"
    assert p.max_output == 16384 and p.vision is True and p.brief_additions == "Answer in one sentence."
    assert issubclass(p, LeanDefault)
    t = harnesses.get("text-only")
    assert t.vision is False and t.extends == "default-text"
    c = harnesses.get("chain")
    assert c.max_output == 2048 and c.brief_additions == "Answer in one sentence."
    assert "small" in [q.id for q in harnesses.for_kind("text")]
    assert harnesses.user_errors() == []


@pytest.mark.parametrize("body,message", [
    ({"extends": "lean-default", "max_output": 0}, "max_output must be"),
    ({"extends": "lean-default", "steps": 4}, "not a field of a text harness"),
    ({"extends": "nothing-like-this"}, "not a harness"),
    ({"extends": "flux.2-klein-9b", "kind": "text"}, "cannot extend"),
    ({"id": "lean-default"}, "already taken"),
])
def test_a_broken_user_harness_is_listed_and_skipped(body, message):
    _user_harness("broken.json", body)
    _user_harness("fine.json", {"extends": "default", "max_output": 4096})
    errs = harnesses.user_errors()
    assert len(errs) == 1 and os.path.basename(errs[0]["file"]) == "broken.json" and message in errs[0]["error"]
    assert harnesses.get("fine").max_output == 4096


def test_a_user_pattern_still_counts_for_a_slot_saved_as_automatic():
    _user_harness("mine.json", {"extends": "lean-default", "patterns": ["q4km"], "max_output": 100000})
    assert harnesses.was_automatic("text", model="qwen3.8-27b-q4km.gguf") == "mine"
    m = dict(settings.slot_defaults("text"), location="http://127.0.0.1:9000", model="qwen3.8-27b-q4km.gguf")
    assert slots.pick("text", None, m)[0] is DefaultText               # ...and for nothing else


def _s(**text):
    s = settings.load()
    settings.active(s)["text"].update(text)
    return s


def test_capabilities_resolve_in_layers():
    s = _s(model="lean-default", script="", harness="lean-default")
    caps = slots.capabilities("text", s)
    assert caps["vision"] == {"value": True, "source": "default"}
    assert caps["max_output"] == {"value": None, "source": "default"}
    s = _s(model="lean-default", script="", harness="lean-default", tested={"vision": False, "max_output": 16384},
           overrides={"max_output": 8000})
    caps = slots.capabilities("text", s)
    assert caps["vision"] == {"value": False, "source": "test"}
    assert caps["max_output"] == {"value": 8000, "source": "override"}


def test_the_harness_is_the_user_s_pick():
    s = _s(model="lean-default", harness="default-text")
    assert slots.pick("text", s)[0] is DefaultText
    assert slots.describe("text", s)["harness"] == {"id": "default-text", "name": "Medium"}


def test_the_shipped_lineups_pick_their_harnesses():
    s = settings.load()
    assert slots.pick("text", s)[0] is DefaultText and slots.pick("image", s)[0] is Flux2Klein9B
    s["lineup"] = "Qwen 3.6 + Klein"
    assert slots.pick("text", s)[0] is LeanDefault


def test_picture_steps():
    klein = {"steps": 4, "steps_range": [4, 12]}
    assert slots.picture_steps(klein) == 4
    assert slots.picture_steps(klein, workflow_steps=12) == 12                       # the workflow's own
    assert slots.picture_steps(klein, requested=6, workflow_steps=12) == 6           # the model asked for 6
    assert slots.picture_steps(klein, requested=30) == 12                         # the model's own: clamped
    assert slots.picture_steps(klein, requested=2) == 4
    user = slots.numbers_in("a fox, 36 steps, seed 8080")
    assert slots.picture_steps(klein, requested=36, user_numbers=user) == 36      # the user's: as written
    assert slots.picture_steps(klein, requested=900, user_numbers={900}) == 150   # the server's own limit


def test_numbers_in_skips_parts_of_words():
    assert slots.numbers_in("qwen3.6 model, 12 steps, v2") == {12}


def test_off_machine():
    s = _s(api="anthropic", location="https://api.anthropic.com")
    assert slots.off_machine("text", s) == "api.anthropic.com"
    assert slots.off_machine("text", _s(location="http://127.0.0.1:8790")) is None


def test_a_user_harness_adds_a_workflow_with_a_lora():
    _user_harness("ink.json", {"extends": "flux.2-klein-9b", "workflows": {"inkWash": {
        "about": "a soft ink wash painting", "prompt": "An ink wash painting of {subject}.", "steps": 8,
        "loras": [{"file": "ink-wash.safetensors", "strength": 0.8}]}}})
    h = harnesses.get("ink")
    assert set(h.workflows) == {COLORING_BOOK, "inkWash"}           # Klein's own stay
    prompt, settings_, missing = h.apply("a heron", "inkWash")
    assert prompt == "An ink wash painting of a heron." and missing is None
    assert settings_ == {"steps": 8, "loras": [{"file": "ink-wash.safetensors", "strength": 0.8}]}
    assert harnesses.user_errors() == []


@pytest.mark.parametrize("wf,message", [
    ({"prompt": "no subject here"}, "workflows must be"),
    ({"prompt": "{subject}", "loras": [{"file": "../outside.safetensors"}]}, "workflows must be"),
    ({"prompt": "{subject}", "reference": "yes"}, "workflows must be"),
    ({"prompt": "{subject}", "seed": 4}, "workflows must be"),
])
def test_a_broken_workflow_is_refused(wf, message):
    _user_harness("bad.json", {"extends": "flux.2-klein-9b", "workflows": {"x": wf}})
    errs = harnesses.user_errors()
    assert len(errs) == 1 and message in errs[0]["error"]


def test_the_shipped_example_harnesses_are_valid_and_not_active():
    folder = os.path.join(os.path.dirname(harnesses.__file__), "examples")
    made, errors = harnesses.load(folder, {p.id: p for p in harnesses.BUILT_IN})
    assert errors == [] and sorted(p.id for p in made) == ["keyword-assists", "klein-turnaround"]
    klein = next(p for p in made if p.id == "klein-turnaround")
    wf = klein.workflow("characterTurnaround")
    assert wf["reference"] is True and wf["loras"][0]["file"].endswith(".safetensors")
    assert COLORING_BOOK in klein.workflows
    for p in made:
        assert harnesses.get(p.id) is None                           # examples are never loaded on their own


def test_shipped_harnesses_are_data_loaded_by_the_users_loader():
    folder = os.path.join(os.path.dirname(harnesses.__file__), "shipped")
    assert sorted(os.listdir(folder)) == ["claude-code.json", "default-image.json", "default-text.json",
                                          "flux.2-klein-9b.json", "lean-default.json", "weak-text.json",
                                          "z-image-turbo.json"]
    assert all(p.source == "shipped" and p.file for p in harnesses.BUILT_IN)
    assert not [n for n in os.listdir(os.path.dirname(harnesses.__file__)) if n.endswith(".py")
                and n not in ("__init__.py", "schema.py", "text.py")]     # the interface; shipped harnesses are data


def test_a_capability_value_adds_request_fields_as_data():
    class H(DefaultText):
        request = {"vision": {"off": {"cache_prompt": True}}}
    assert H().tune({"model": "m"}, {"vision": "off"}) == {"model": "m", "cache_prompt": True}
    assert H().tune({"model": "m"}, {"vision": "on"}) == {"model": "m"}


def test_the_folder_holds_a_guide_per_kind_and_only_the_users_harnesses():
    folder = harnesses.user_folder()
    for sub in ("llm", "image"):
        assert os.listdir(os.path.join(folder, sub)) == [harnesses.GUIDE]       # the app's harnesses are in the app
    assert sorted(os.listdir(folder)) == ["image", "llm"]
    with open(os.path.join(folder, "llm", harnesses.GUIDE), encoding="utf-8") as f:
        assert f.read().startswith("# How to create a new LLM harness")
    with open(os.path.join(folder, "image", harnesses.GUIDE), encoding="utf-8") as f:
        assert "## Workflows" in f.read()


def test_a_python_harness_overrides_what_it_changes():
    folder = os.path.join(harnesses.user_folder(), "llm")
    with open(os.path.join(folder, "terse.py"), "w", encoding="utf-8") as f:
        f.write("""import statistics
from paperdaemon import harnesses


class Terse(harnesses.get("lean-default")):
    id = "terse"
    name = "llama.cpp - Qwen 3.8 27B, terse"
    server = "llama.cpp (llama-server)"
    models = ["Qwen 3.8 27B"]

    def nudge_no_call(self, said, allowed):
        return [{"role": "user", "content": "Call %s." % allowed[0]}]
""")
    with open(os.path.join(folder, "broken.py"), "w", encoding="utf-8") as f:
        f.write("raise ValueError('half written')\n")
    with open(os.path.join(folder, "nameless.py"), "w", encoding="utf-8") as f:
        f.write("from paperdaemon import harnesses\nclass X(harnesses.DEFAULT['text']):\n    pass\n")
    t = harnesses.get("terse")
    assert t is not None and t.extends == "lean-default" and t.source == "user"
    assert t().nudge_no_call("", ("plan",)) == [{"role": "user", "content": "Call plan."}]
    assert t.vision is True and t().locate_one is not None             # the rest is inherited
    errs = {e["file"]: e["error"] for e in harnesses.user_errors()}
    assert "half written" in errs[os.path.join("llm", "broken.py")]
    assert "server" in errs[os.path.join("llm", "nameless.py")]


def test_a_skills_only_harness_changes_only_its_skills():
    base = os.path.join(harnesses.user_folder(), "llm", "plain-words")
    os.makedirs(os.path.join(base, "skills"))
    with open(os.path.join(base, "harness.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "llama.cpp - Qwen 3.8 27B, plain words", "extends": "lean-default",
                   "server": "llama.cpp (llama-server)", "models": ["Qwen 3.8 27B"]}, f)
    with open(os.path.join(base, "skills", "write.md"), "w", encoding="utf-8") as f:
        f.write("Use plain words.")
    h = harnesses.get("plain-words")
    assert h is not None and h.extends == "lean-default"
    assert h().skill("write", "default") == "Use plain words." and h().skill("draw", "default") == "default"

def test_every_harness_file_says_its_server_and_models():
    _user_harness("bare.json", {"extends": "lean-default", "max_output": 1000}, declared=False)
    errs = {e["file"]: e["error"] for e in harnesses.user_errors()}
    assert "server" in errs[os.path.join("llm", "bare.json")] and "models" in errs[os.path.join("llm", "bare.json")]
    for p in harnesses.BUILT_IN:                                     # the shipped ones say theirs
        assert p.server and p.models
    named = {p.id: p.name for p in harnesses.SHIPPED}
    assert named["lean-default"] == "Strong"
    _user_harness("mine.json", {"extends": "lean-default"})
    mine = harnesses.get("mine")
    assert mine.server == "a test server" and mine.models == ("a test model",)
    assert harnesses.get("lean-default").server.startswith("Any ")           # never inherited the other way


def test_every_harness_to_pick_describes_itself_for_the_lineup_screen():
    """'the header block should be in code on the harness, and should be pulled into the lineup': what it is for, what a
    model must be able to do on it, and what a heavier harness costs a stronger model."""
    for kind in ("text", "image"):
        for h in harnesses.for_kind(kind):
            said = harnesses.describe(h)["notes"]
            assert len(said) > 80 and said == h.notes, h.id          # the file's own words, as the API lists them
    d, lean = DefaultText.notes, LeanDefault.notes
    assert "Full instructions, and each step of a job is its own call." in d
    assert "most jobs finish in one call, so it uses the fewest tokens" in lean and "A weaker model will skip work" in lean
    assert "guess" not in (d + lean + Flux2Klein9B.notes + ZImageTurbo.notes + DefaultImage.notes).lower()
    assert "refused" not in Flux2Klein9B.notes                     # (it spoke of a hint a guess refused; nothing guesses)
