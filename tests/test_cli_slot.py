"""A text slot whose source is a command line (models/cli.py): a program on this computer, run once a turn, EXACTLY as
the user typed it. PaperDaemon ships nothing particular to any program and adds nothing to a command: the system text
and the conversation go on its input, a page's pictures as files named in the words, its answer is what it prints
(the maintainer, 11-15: no program-specific harness; the three things that needed one -- token counts, an output
limit, a sign-in check -- are not needed)."""
import json
import os
import sys

from paperdaemon import harnesses, settings
from paperdaemon.models import adapters, cli as C

TOOLS = [{"name": "answer", "description": "Answer in words.",
          "parameters": {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
                         "required": ["lines"]}},
         {"name": "skip", "description": "Do nothing.", "parameters": {"type": "object", "properties": {}}}]
SLOT = dict(settings.slot_defaults("text"), api="cli", location="some-program -p --model big --effort medium",
            harness="lean-default")


def test_the_slot_is_a_setting_like_any_other():
    assert "cli" in settings.APIS["text"] and settings.check_slot("text", SLOT) == []
    assert settings.check_slot("text", dict(SLOT, location="C:\\Program Files\\Tool\\tool.exe --fast")) == []   # no URL asked
    assert settings.check_slot("text", dict(SLOT, location="a\nb")) != []
    assert type(adapters.for_slot("text", None, SLOT)).__name__ == "CommandLine"
    assert adapters.for_slot("text", None, SLOT).key is None                 # no key is looked up for a command
    other = {"api": "cli", "location": "some-other-program -x", "model": "m"}
    assert settings.upgrade_slot(other) == {"api": "cli", "location": "some-other-program -x", "model": ""}


def test_nothing_particular_to_a_program_ships():
    """No shipped harness says how a program is run, no harness takes a field for it, and the adapter names none."""
    src = open(C.__file__, encoding="utf-8").read().lower()
    assert "claude" not in src and "anthropic" not in src
    folder = os.path.join(os.path.dirname(harnesses.__file__), "shipped")
    for f in os.listdir(folder):
        d = json.load(open(os.path.join(folder, f), encoding="utf-8"))
        assert "cli" not in d and "claude" not in json.dumps(d.get("id", "")), f
    assert "cli" not in harnesses.get("lean-default").FIELDS


def test_a_command_runs_exactly_as_typed(tmp_path):
    """Nothing is added to the user's command: no argument, no model, no effort, no tools, no environment."""
    a = C.CommandLine("some-program -p --model big --effort medium --tools Read")
    hp = harnesses.get("lean-default")()
    args, stdin, system, dropped = a.request("You work on a page.", [{"role": "user", "text": "hi"}], tools=TOOLS,
                                             force_tool=True, caps={"vision": True, "forced_tool": True}, harness=hp,
                                             max_tokens=16384, folder=str(tmp_path))
    assert args == []
    assert C.find(a.command)[1] == ["-p", "--model", "big", "--effort", "medium", "--tools", "Read"]
    assert stdin.startswith("You work on a page.") and "HOW TO ANSWER" in stdin and "[THE USER'S SIDE]\nhi" in stdin
    assert "At least one call is required." in stdin and a.model == ""


def test_a_picture_goes_to_the_program_as_a_file_it_opens(tmp_path):
    """The one way to show any program a page: the picture saved in the run's folder (its working folder), named in
    the words where it is. The program opens it as its own command allows (11-15: a real program read a page so)."""
    a = C.CommandLine("some-program -p")
    run = tmp_path / "run"
    run.mkdir()
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "What is the title?", "images": [b"PNG1", b"PNG2"]}],
                                             caps={"vision": True}, folder=str(run))
    assert dropped == 0 and sorted(os.listdir(run)) == ["picture-1.png", "picture-2.png"]
    assert (run / "picture-2.png").read_bytes() == b"PNG2"
    assert "[PICTURE: picture-1.png, a file in the current folder; open it to see it]\n" \
           "[PICTURE: picture-2.png, a file in the current folder; open it to see it]\n[THE USER'S SIDE]" in stdin
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi", "images": [b"x"]}], caps={"vision": False},
                                             folder=str(run))
    assert dropped == 1 and "PICTURE" not in stdin                       # a model that cannot see is sent none


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


def test_a_job_s_later_call_begins_exactly_as_its_first(tmp_path):
    """A provider reads a call's beginning from its cache only when it matches the call before byte for byte: the page,
    its first turn (its picture named the same way), is written the same way alone and with turns after it."""
    a = C.CommandLine("some-program -p")
    page = {"role": "user", "text": "THE PAGE", "images": [b"png"]}
    later = [page, {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "answer", "arguments": {}}]},
             {"role": "tool", "tool_call_id": "c1", "name": "answer", "text": "ok"}]
    for d in ("1", "2"):
        (tmp_path / d).mkdir()
    one = a.request("sys", [page], caps={"vision": True}, harness=harnesses.DEFAULT["text"](), folder=str(tmp_path / "1"))[1]
    two = a.request("sys", later, caps={"vision": True}, harness=harnesses.DEFAULT["text"](), folder=str(tmp_path / "2"))[1]
    assert two.startswith(one.strip())


def test_a_program_is_run_and_its_printed_answer_read(tmp_path):
    """A real program: Python itself, told to print an answer. The system text and the conversation go on its input,
    the picture is a file in its working folder, what it prints is the answer; with tools, the JSON object in it."""
    echo = tmp_path / "echo.py"
    echo.write_text("import sys\ntext = sys.stdin.read()\nprint('GOT ' + str(len(text)) + ' ' + ('tools' if 'HOW TO ANSWER' in text else 'plain'))\n",
                    encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, echo))
    assert a.health() and a.models() == []
    r = a.chat("sys", [{"role": "user", "text": "say ready"}])
    assert r["text"].startswith("GOT ") and r["text"].endswith("plain") and r["tool_calls"] == []
    calls = tmp_path / "calls.py"
    calls.write_text("import os\nassert os.path.isfile('picture-1.png')\n"
                     "print('Here you go:\\n```json\\n{\"text\": \"\", \"tool_calls\": [{\"name\": \"answer\", \"arguments\": {\"lines\": [\"Lima.\"]}},"
                     " {\"name\": \"not-a-tool\", \"arguments\": {}}]}\\n```')\n", encoding="utf-8")
    a = C.CommandLine('"%s" "%s"' % (sys.executable, calls))
    r = a.chat("sys", [{"role": "user", "text": "capital of Peru?", "images": [b"x"]}], tools=TOOLS, force_tool=True,
               caps={"vision": True})
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"lines": ["Lima."]})]
    assert r["stop"] == "tool_use" and r["dropped_images"] == 0 and r["usage"] == {}
    assert not [n for n in os.listdir(C.paths.sub("cache", "cli")) if n.startswith("run-")]   # nothing left behind
    fails = tmp_path / "fails.py"
    fails.write_text("import sys\nsys.stderr.write('not signed in')\nsys.exit(3)\n", encoding="utf-8")
    try:
        C.CommandLine('"%s" "%s"' % (sys.executable, fails)).chat("sys", [{"role": "user", "text": "hi"}])
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "stopped (3)" in str(ex) and "not signed in" in str(ex)    # the program's own words, as it said them
    missing = C.CommandLine("no-such-program-here")
    assert not missing.health() and C.ready("no-such-program-here")[0] is False
    try:
        missing.chat("sys", [{"role": "user", "text": "hi"}])
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "no-such-program-here" in str(ex) and "not found" in str(ex)


def test_calls_written_in_tool_call_markup_are_read():
    """A model sometimes answered with the tool-call markup it was trained on instead of the JSON it was asked for;
    each time cost two more calls to be asked again. The markup is read as the calls it names."""
    said = ('<invoke name="answer">\n<parameter name="answers">["para:1"]</parameter>\n'
            '<parameter name="lines">["Lima is the capital."]</parameter>\n</invoke>')
    r = C.CommandLine.parse(said, TOOLS)
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"answers": ["para:1"], "lines": ["Lima is the capital."]})]
    plain = '<invoke name="skip"><parameter name="note">nothing here</parameter></invoke>'
    assert C.CommandLine.parse(plain, TOOLS)["tool_calls"][0]["arguments"] == {"note": "nothing here"}


def test_a_program_installed_after_paperdaemon_started_is_found(monkeypatch, tmp_path):
    """A program put on the PATH after PaperDaemon started is found on the system's PATH as it is now (11-15: a program
    installed while PaperDaemon ran, and its lineup's test said no answer)."""
    exe = tmp_path / ("newprog.exe" if os.name == "nt" else "newprog")
    exe.write_text("")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(C, "_path_now", lambda: str(tmp_path))
    assert C.find("newprog -p")[0] and C.ready("newprog")[0]
    monkeypatch.setattr(C, "_path_now", lambda: "")
    assert C.find("newprog -p")[0] is None


def test_the_test_names_a_program_that_is_not_found(monkeypatch):
    from paperdaemon.models import hotswap
    m = dict(SLOT, location="no-such-program-here -p")
    st = hotswap.status("text", None, m)
    assert st["answering"] is False and st["missing_program"] == "no-such-program-here"
