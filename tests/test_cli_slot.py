"""A text slot whose source is a command line (models/cli.py): a program on this computer, run once a turn. The
adapter knows no program: how one is spoken to -- its arguments, its input, where its answer is, its readiness, where
it sends a page -- is the `cli` field of a harness. The shipped harness for the command `claude` is that data and
nothing more."""
import json
import os
import sys
import types

from paperdaemon import harnesses, settings
from paperdaemon.harnesses import schema
from paperdaemon.models import adapters, cli as C, slots

TOOLS = [{"name": "answer", "description": "Answer in words.",
          "parameters": {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
                         "required": ["lines"]}},
         {"name": "skip", "description": "Do nothing.", "parameters": {"type": "object", "properties": {}}}]
SLOT = dict(settings.slot_defaults("text"), api="cli", location="claude", model="claude-opus-5-5")


def test_the_slot_is_a_setting_like_any_other_and_an_earlier_version_s_is_upgraded():
    assert "cli" in settings.APIS["text"] and settings.check_slot("text", SLOT) == []
    assert settings.check_slot("text", dict(SLOT, location="C:\\Program Files\\Tool\\tool.exe --fast")) == []   # no URL asked
    assert settings.check_slot("text", dict(SLOT, location="a\nb")) != []
    assert type(adapters.for_slot("text", None, SLOT)).__name__ == "CommandLine"
    assert adapters.for_slot("text", None, SLOT).key is None                 # no key is looked up for a command
    old = {"api": "claude-cli", "location": "https://api.anthropic.com/claude-code", "model": "claude-opus-5-5"}
    assert settings.upgrade_slot(old) == {"api": "cli", "location": "claude", "model": "claude-opus-5-5"}


def test_nothing_in_the_adapter_names_a_program():
    src = open(C.__file__, encoding="utf-8").read().lower()
    assert "claude" not in src and "anthropic" not in src and "structuredoutput" not in src


def test_the_harness_made_for_the_program_speaks_for_it():
    assert slots.pick("text", None, SLOT)[0].id == "claude-opus-5.5"          # by the model's name, as always
    assert harnesses.get("claude-opus-5.5").cli["program"] == "claude"         # which extends the program's harness
    plain = dict(SLOT, model="some-other-model")
    assert slots.pick("text", None, plain)[0].id == "default-text"            # no harness for that model...
    assert C.cli_of(slots.pick("text", None, plain)[0], "claude --verbose")["program"] == "claude"   # ...the program's speaks
    assert C.cli_of(harnesses.DEFAULT["text"], "some-other-program") is C.PLAIN
    assert C.name_of('"C:\\Tools\\Claude.EXE" --x') == "claude"
    # where a page goes is the harness's to say; a program that says nothing keeps it here
    assert slots.pages_go_to("text", None, SLOT) == "api.anthropic.com"
    assert slots.pages_go_to("text", None, dict(plain, location="some-other-program")) is None
    assert schema.check("cli", harnesses.get("claude-code").cli) is None
    assert schema.check("cli", {"args": [["--x", 3]]}) is not None and schema.check("cli", {"nope": 1}) is not None


def test_a_request_is_built_from_the_harness_s_data(tmp_path):
    a = C.CommandLine("claude", None, "claude-opus-5-5")
    hp = harnesses.get("claude-opus-5.5")()
    args, stdin, system, dropped = a.request("You work on a page.", [{"role": "user", "text": "hi", "images": [b"png"]}],
                                             tools=TOOLS, force_tool=True, caps={"vision": True, "forced_tool": True},
                                             harness=hp, folder=str(tmp_path))
    pairs = dict(zip(args, args[1:]))
    assert args[0] == "-p" and pairs["--tools"] == "" and pairs["--model"] == "claude-opus-5-5"
    assert pairs["--effort"] == "medium"                                   # {request.output_config.effort}, the harness's
    calls = json.loads(pairs["--json-schema"])["properties"]["tool_calls"]
    assert calls["minItems"] == 1 and [c["properties"]["name"]["const"] for c in calls["items"]["anyOf"]] == ["answer", "skip"]
    assert open(pairs["--system-prompt-file"], encoding="utf-8").read() == system
    assert system.startswith("You work on a page.") and "- answer: Answer in words." in system
    assert "Give it through StructuredOutput." in system                   # the harness's own sentence
    sent = json.loads(stdin)["message"]["content"]
    assert [b["type"] for b in sent] == ["image", "text"] and sent[1]["text"] == "hi" and dropped == 0
    assert sent[0]["source"] == {"type": "base64", "media_type": "image/png", "data": adapters._b64(b"png")}
    # a group whose placeholder has nothing to give is left out whole: no effort without a harness, no schema without tools
    args, stdin, system, dropped = a.request("", [{"role": "user", "text": "hi", "images": [b"a", b"b"]}], caps={"vision": False},
                                             folder=str(tmp_path))
    assert "--effort" not in args and "--json-schema" not in args and dropped == 2
    assert [b["type"] for b in json.loads(stdin)["message"]["content"]] == ["text"]


def test_an_argument_typed_in_the_command_stands_over_the_harness_s(tmp_path):
    # "Can the cli have a parameter, maybe?" -- the command is typed as in a terminal, its own arguments included
    a = C.CommandLine("claude --effort high --model sonnet", None, "claude-opus-5-5")
    hp = harnesses.get("claude-opus-5.5")()
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi"}], caps={"vision": True}, harness=hp,
                                             folder=str(tmp_path))
    assert "--effort" not in args and "--model" not in args and "--system-prompt-file" in args
    assert C.find("claude --effort high --model sonnet", hp.cli)[1] == ["--effort", "high", "--model", "sonnet"]


def test_a_conversation_goes_as_turns_a_later_request_begins_with():
    msgs = [{"role": "user", "text": "Record apple."},
            {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "record", "arguments": {"word": "apple"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "record", "text": "recorded"}]
    first, _ = C.turns_of(msgs[:2], True)
    later, _ = C.turns_of(msgs, True)
    assert later[:2] == first[:2]
    assert later[1][1] == '[YOUR EARLIER TURN]\ncalled record({"word": "apple"})'
    assert later[2][1] == "[RESULT OF record]\nrecorded" and later[-1][1].startswith("[NOW]")


def test_a_program_with_no_harness_is_spoken_to_the_plainest_way(tmp_path):
    """A real program: Python itself, told to print an answer. The system text and the conversation go on its input;
    what it prints is the answer; with tools, the JSON object in what it prints is read."""
    echo = tmp_path / "echo.py"
    echo.write_text("import sys\ntext = sys.stdin.read()\nprint('GOT ' + str(len(text)) + ' ' + ('tools' if 'HOW TO ANSWER' in text else 'plain'))\n",
                    encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, echo), None, "any")
    assert a.health() and a.models() == []
    r = a.chat("sys", [{"role": "user", "text": "say ready"}])
    assert r["text"].startswith("GOT ") and r["text"].endswith("plain") and r["tool_calls"] == []
    calls = tmp_path / "calls.py"
    calls.write_text("print('Here you go:\\n```json\\n{\"text\": \"\", \"tool_calls\": [{\"name\": \"answer\", \"arguments\": {\"lines\": [\"Lima.\"]}},"
                     " {\"name\": \"not-a-tool\", \"arguments\": {}}]}\\n```')\n", encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, calls), None, "any")
    r = a.chat("sys", [{"role": "user", "text": "capital of Peru?", "images": [b"x"]}], tools=TOOLS, force_tool=True,
               caps={"vision": True})
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"lines": ["Lima."]})]
    assert r["stop"] == "tool_use" and r["dropped_images"] == 1          # the plain way has nowhere for a picture
    # nothing is left behind in the folder the runs were made in
    assert not [n for n in os.listdir(C.paths.sub("cache", "cli")) if n.startswith("run-")]
    missing = C.CommandLine("no-such-program-here", None, "any")
    assert not missing.health()
    try:
        missing.chat("sys", [{"role": "user", "text": "hi"}])
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "no-such-program-here" in str(ex) and "not found" in str(ex)


def test_what_the_program_prints_is_read_as_the_harness_says():
    cli = harnesses.get("claude-code").cli
    out = "\n".join([json.dumps({"type": "system", "tools": ["x"]}),
                     json.dumps({"type": "result", "is_error": False, "result": "",
                                 "structured_output": {"text": "", "tool_calls": [{"name": "answer", "arguments": {"lines": ["Lima."]}}]},
                                 "usage": {"input_tokens": 2, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 100,
                                           "output_tokens": 7}})])
    r = C.CommandLine.parse(out, TOOLS, cli, "claude")
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"lines": ["Lima."]})]
    assert r["usage"] == {"input": 112, "output": 7, "cached": 100}
    plain = json.dumps({"type": "result", "is_error": False, "result": "ready"})
    assert C.CommandLine.parse(plain, (), cli, "claude")["text"] == "ready"
    failed = json.dumps({"type": "result", "is_error": True, "result": "usage limit reached"})
    for bad, said in ((failed, "usage limit reached"), ("not json at all", "gave no answer")):
        try:
            C.CommandLine.parse(bad, (), cli, "claude")
            raise AssertionError("no error")
        except adapters.AdapterError as ex:
            assert said in str(ex)


def test_readiness_is_the_harness_s_check(monkeypatch):
    cli = dict(harnesses.get("claude-code").cli)
    monkeypatch.setattr(C, "find", lambda command, c=None: ("claude.exe", []))
    monkeypatch.setattr(C, "_run", lambda exe, args, stdin=None, folder=None: types.SimpleNamespace(
        returncode=0, stdout='{"loggedIn": false}', stderr=""))
    assert C.ready("claude", cli) == (False, "claude is not signed in on this computer: run `claude` once and sign in")
    monkeypatch.setattr(C, "_run", lambda exe, args, stdin=None, folder=None: types.SimpleNamespace(
        returncode=0, stdout='{"loggedIn": true}', stderr=""))
    assert C.ready("claude", cli) == (True, "")
    assert C.ready("anything", C.PLAIN) == (True, "")                     # found, and no check asked: ready


def test_a_schema_too_long_for_a_command_line_goes_loose_with_the_tools_schemas_in_the_system_text(tmp_path):
    big = [{"name": "t%d" % i, "description": "d", "parameters": {"type": "object", "properties": {
        "p%d" % k: {"type": "string", "description": "x" * 200} for k in range(12)}}} for i in range(14)]
    a = C.CommandLine("claude", None, "opus")
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi"}], tools=big, caps={"vision": True},
                                             harness=harnesses.get("claude-code")(), folder=str(tmp_path))
    sch = json.loads(args[args.index("--json-schema") + 1])
    assert sch["properties"]["tool_calls"]["items"]["anyOf"][0]["properties"]["arguments"] == {"type": "object"}
    assert "arguments (JSON schema):" in system
