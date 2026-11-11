"""A text slot whose source is a command line (models/cli.py): a program on this computer, run once a turn. The
adapter knows no program: how one is spoken to -- its arguments, its input, where its answer is, its readiness, where
it sends a page -- is the `cli` field of a harness. The shipped harness for the command `claude` is that data and
nothing more. The command is WHOLE: the model and the effort are arguments the user types in it; no field beside it
names a model, no harness sets an effort, and nothing reads the command to choose a harness."""
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
SLOT = dict(settings.slot_defaults("text"), api="cli", location="claude --model claude-opus-5-5 --effort medium",
            harness="lean-default")


def test_the_slot_is_a_setting_like_any_other_and_an_earlier_version_s_is_upgraded():
    assert "cli" in settings.APIS["text"] and settings.check_slot("text", SLOT) == []
    assert settings.check_slot("text", dict(SLOT, location="C:\\Program Files\\Tool\\tool.exe --fast")) == []   # no URL asked
    assert settings.check_slot("text", dict(SLOT, location="a\nb")) != []
    assert type(adapters.for_slot("text", None, SLOT)).__name__ == "CommandLine"
    assert adapters.for_slot("text", None, SLOT).key is None                 # no key is looked up for a command
    # 0.2.39 to 0.2.41 had a source for one program, 0.2.42 to 0.2.47 a model field beside the command: both become
    # the one command, which names its model the program's own way (the program's data says which argument that is)
    old = {"api": "claude-cli", "location": "https://api.anthropic.com/claude-code", "model": "claude-opus-5-5"}
    assert settings.upgrade_slot(old) == {"api": "cli", "location": "claude --model claude-opus-5-5", "model": ""}
    kept = {"api": "cli", "location": "claude --model sonnet", "model": "claude-opus-5-5"}
    assert settings.upgrade_slot(kept) == {"api": "cli", "location": "claude --model sonnet", "model": ""}   # the command's own stands
    other = {"api": "cli", "location": "some-other-program -x", "model": "m"}
    assert settings.upgrade_slot(other) == {"api": "cli", "location": "some-other-program -x", "model": ""}  # no argument known for it


def test_the_command_is_the_user_s_and_nothing_is_read_out_of_it():
    """'its stupid to have both a Command field and a Model field'; 'ZERO inference from paperdaemons perspective'."""
    cli = harnesses.get("claude-code").cli
    assert "model_arg" not in cli and not any(isinstance(a, list) and a[0] in ("--model", "--effort") for a in cli["args"])
    a = C.CommandLine("claude --model haiku")
    assert a.model == "" and a.models() == []
    for command in ("claude --model claude-opus-5-5", "claude --model sonnet", "claude"):
        m = dict(settings.slot_defaults("text"), api="cli", location=command)
        assert slots.pick("text", None, m)[0].id == "default-text"         # the harness is the slot's own, whatever the command
    offered = [h.id for h in harnesses.for_kind("text")]
    assert "claude-code" not in offered and harnesses.get("claude-code") is not None     # the program's data is not one to pick
    assert harnesses.describe(harnesses.get("claude-code"))["offered"] is False


def test_nothing_in_the_adapter_names_a_program():
    src = open(C.__file__, encoding="utf-8").read().lower()
    assert "claude" not in src and "anthropic" not in src and "structuredoutput" not in src


def test_the_harness_made_for_the_program_speaks_for_it():
    assert slots.pick("text", None, SLOT)[0].id == "lean-default"             # the one the slot names
    assert not harnesses.get("lean-default").cli                               # which says nothing of a program...
    assert C.cli_of(harnesses.get("lean-default"), SLOT["location"])["program"] == "claude"      # ...the program's data speaks
    plain = dict(SLOT, harness="default-text")
    assert C.cli_of(slots.pick("text", None, plain)[0], "claude --verbose")["program"] == "claude"   # under any harness
    assert C.cli_of(harnesses.DEFAULT["text"], "some-other-program") is C.PLAIN
    assert C.name_of('"C:\\Tools\\Claude.EXE" --x') == "claude"
    # where a page goes is the harness's to say; a program that says nothing keeps it here
    assert slots.pages_go_to("text", None, SLOT) == "api.anthropic.com"
    assert slots.pages_go_to("text", None, dict(plain, location="some-other-program")) is None
    assert schema.check("cli", harnesses.get("claude-code").cli) is None
    assert schema.check("cli", {"args": [["--x", 3]]}) is not None and schema.check("cli", {"nope": 1}) is not None


def test_a_request_is_built_from_the_harness_s_data(tmp_path):
    a = C.CommandLine("claude --model claude-opus-5-5 --effort medium")
    hp = harnesses.get("lean-default")()
    args, stdin, system, dropped = a.request("You work on a page.", [{"role": "user", "text": "hi", "images": [b"png"]}],
                                             tools=TOOLS, force_tool=True, caps={"vision": True, "forced_tool": True},
                                             harness=hp, folder=str(tmp_path))
    pairs = dict(zip(args, args[1:]))
    assert args[0] == "-p" and pairs["--tools"] == ""
    assert "--model" not in args and "--effort" not in args                # the command's own, typed by the user: never added
    assert C.find(a.command, a.cli(hp))[1] == ["--model", "claude-opus-5-5", "--effort", "medium"]
    # THE CALLS COME BACK AS ONE JSON OBJECT IN THE ANSWER'S WORDS, checked by PaperDaemon: this program, asked to check
    # them against a schema, makes a second request for every answer (measured: 15,109 tokens in, where 5,978 do)
    assert "--json-schema" not in args
    assert open(pairs["--system-prompt-file"], encoding="utf-8").read() == system
    assert system.startswith("You work on a page.") and "- answer: Answer in words." in system
    assert "HOW TO ANSWER" in system and "arguments (JSON schema):" in system and "At least one call is required." in system
    # a program that does check an answer against a schema is handed it, and told its own way to give the answer
    checking = dict(a.cli(hp), answer_rule="Give it through the answer tool.")
    checking["args"] = list(checking["args"]) + [["--answer-schema", "{schema}"]]
    hc = type("Checking", (harnesses.get("lean-default"),), {"cli": checking})()
    args_c, _in, system_c, _d = a.request("You work on a page.", [{"role": "user", "text": "hi"}], tools=TOOLS, force_tool=True,
                                          caps={"vision": True, "forced_tool": True}, harness=hc, folder=str(tmp_path))
    calls = json.loads(dict(zip(args_c, args_c[1:]))["--answer-schema"])["properties"]["tool_calls"]
    assert calls["minItems"] == 1 and [c["properties"]["name"]["const"] for c in calls["items"]["anyOf"]] == ["answer", "skip"]
    assert "Give it through the answer tool." in system_c and "arguments (JSON schema):" not in system_c
    sent = json.loads(stdin)["message"]["content"]
    assert [b["type"] for b in sent] == ["image", "text"] and sent[1]["text"] == "[THE USER'S SIDE]\nhi" and dropped == 0
    assert sent[0]["source"] == {"type": "base64", "media_type": "image/png", "data": adapters._b64(b"png")}
    # a group whose placeholder has nothing to give is left out whole: no schema without tools
    args, stdin, system, dropped = a.request("", [{"role": "user", "text": "hi", "images": [b"a", b"b"]}], caps={"vision": False},
                                             folder=str(tmp_path))
    assert "--json-schema" not in args and dropped == 2
    assert [b["type"] for b in json.loads(stdin)["message"]["content"]] == ["text"]


def test_an_argument_typed_in_the_command_stands_over_the_harness_s(tmp_path):
    # "Can the cli have a parameter, maybe?" -- the command is typed as in a terminal, its own arguments included
    a = C.CommandLine("claude --effort high --model sonnet --system-prompt-file mine.txt")
    hp = harnesses.get("lean-default")()
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi"}], caps={"vision": True}, harness=hp,
                                             folder=str(tmp_path))
    assert "--system-prompt-file" not in args and "--no-session-persistence" in args      # a group the user gave is left out
    assert C.find(a.command, a.cli(hp))[1] == ["--effort", "high", "--model", "sonnet", "--system-prompt-file", "mine.txt"]


def test_a_conversation_goes_as_turns_a_later_request_begins_with():
    msgs = [{"role": "user", "text": "Record apple."},
            {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "record", "arguments": {"word": "apple"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "record", "text": "recorded"}]
    first, _ = C.turns_of(msgs[:2], True)
    later, _ = C.turns_of(msgs, True)
    assert later[:2] == first[:2]            # every turn worded as in the call before, so the provider's cache holds
    assert C.turns_of(msgs[:1], True)[0][0][1].startswith("[THE USER'S SIDE]")
    assert later[1][1] == '[YOUR EARLIER TURN]\ncalled record({"word": "apple"})'
    assert later[2][1] == "[RESULT OF record]\nrecorded" and later[-1][1].startswith("[NOW]")


def test_a_program_with_no_harness_is_spoken_to_the_plainest_way(tmp_path):
    """A real program: Python itself, told to print an answer. The system text and the conversation go on its input;
    what it prints is the answer; with tools, the JSON object in what it prints is read."""
    echo = tmp_path / "echo.py"
    echo.write_text("import sys\ntext = sys.stdin.read()\nprint('GOT ' + str(len(text)) + ' ' + ('tools' if 'HOW TO ANSWER' in text else 'plain'))\n",
                    encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, echo))
    assert a.health() and a.models() == []
    r = a.chat("sys", [{"role": "user", "text": "say ready"}])
    assert r["text"].startswith("GOT ") and r["text"].endswith("plain") and r["tool_calls"] == []
    calls = tmp_path / "calls.py"
    calls.write_text("print('Here you go:\\n```json\\n{\"text\": \"\", \"tool_calls\": [{\"name\": \"answer\", \"arguments\": {\"lines\": [\"Lima.\"]}},"
                     " {\"name\": \"not-a-tool\", \"arguments\": {}}]}\\n```')\n", encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, calls))
    r = a.chat("sys", [{"role": "user", "text": "capital of Peru?", "images": [b"x"]}], tools=TOOLS, force_tool=True,
               caps={"vision": True})
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"lines": ["Lima."]})]
    assert r["stop"] == "tool_use" and r["dropped_images"] == 1          # the plain way has nowhere for a picture
    # nothing is left behind in the folder the runs were made in
    assert not [n for n in os.listdir(C.paths.sub("cache", "cli")) if n.startswith("run-")]
    missing = C.CommandLine("no-such-program-here")
    assert not missing.health()
    try:
        missing.chat("sys", [{"role": "user", "text": "hi"}])
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "no-such-program-here" in str(ex) and "not found" in str(ex)


def test_what_the_program_prints_is_read_as_the_harness_says():
    cli = harnesses.get("claude-code").cli
    out = "\n".join([json.dumps({"type": "system", "tools": ["x"]}),
                     json.dumps({"type": "result", "is_error": False,
                                 "result": json.dumps({"text": "", "tool_calls": [{"name": "answer", "arguments": {"lines": ["Lima."]}}]}),
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
    a = C.CommandLine("claude --model opus")
    checking = dict(harnesses.get("claude-code").cli)
    checking["args"] = list(checking["args"]) + [["--json-schema", "{schema}"]]
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi"}], tools=big, caps={"vision": True},
                                             harness=type("Checking", (harnesses.get("claude-code"),), {"cli": checking})(),
                                             folder=str(tmp_path))
    sch = json.loads(args[args.index("--json-schema") + 1])
    assert sch["properties"]["tool_calls"]["items"]["anyOf"][0]["properties"]["arguments"] == {"type": "object"}
    assert "arguments (JSON schema):" in system


def test_a_job_s_later_call_begins_exactly_as_its_first():
    """The provider reads a call's beginning from its cache only when it matches the call before byte for byte: the
    page, its first turn, is written the same way alone and with turns after it."""
    a = C.CommandLine("claude --model opus")
    page = {"role": "user", "text": "THE PAGE", "images": [b"png"]}
    later = [page, {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "answer", "arguments": {}}]},
             {"role": "tool", "tool_call_id": "c1", "name": "answer", "text": "ok"}]
    one = json.loads(a.request("sys", [page], caps={"vision": True}, harness=harnesses.DEFAULT["text"]())[1])
    two = json.loads(a.request("sys", later, caps={"vision": True}, harness=harnesses.DEFAULT["text"]())[1])
    n = len(one["message"]["content"])
    assert two["message"]["content"][:n] == one["message"]["content"]


def test_calls_written_in_tool_call_markup_are_read():
    """Sonnet 5.5 sometimes answered with the tool-call markup it was trained on instead of the JSON it was asked for;
    each time cost two more calls to be asked again. The markup is read as the calls it names."""
    cli = harnesses.get("claude-code").cli
    said = ('<invoke name="answer">\n<parameter name="answers">["para:1"]</parameter>\n'
            '<parameter name="lines">["Lima is the capital."]</parameter>\n</invoke>')
    out = json.dumps({"type": "result", "is_error": False, "result": said, "usage": {}})
    r = C.CommandLine.parse(out, TOOLS, cli, "claude")
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"answers": ["para:1"], "lines": ["Lima is the capital."]})]
    plain = json.dumps({"type": "result", "is_error": False, "result": '<invoke name="skip"><parameter name="note">nothing here</parameter></invoke>'})
    assert C.CommandLine.parse(plain, TOOLS, cli, "claude")["tool_calls"][0]["arguments"] == {"note": "nothing here"}
