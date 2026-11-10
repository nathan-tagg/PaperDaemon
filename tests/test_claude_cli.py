"""A text slot served by Claude Code, the program on this computer (models/claude_cli.py): PaperDaemon starts it as
published and reads what it prints -- no tools of its own, no settings or MCP servers of the user's, no session kept,
never its sign-in; the host's tools as one schema; the effort from the harness's request, the field the API takes."""
import json
import types

from paperdaemon import harnesses, settings
from paperdaemon.models import adapters, claude_cli as CC, slots

TOOLS = [{"name": "answer", "description": "Answer in words.",
          "parameters": {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
                         "required": ["lines"]}},
         {"name": "skip", "description": "Do nothing.", "parameters": {"type": "object", "properties": {}}}]
SLOT = dict(settings.slot_defaults("text"), api="claude-cli", location=CC.WHERE, model="claude-opus-5-5")


def _printed(structured=None, text="", error=False):
    return "\n".join([json.dumps({"type": "system", "tools": ["StructuredOutput"]}),
                      json.dumps({"type": "result", "subtype": "success", "is_error": error, "result": text,
                                  "structured_output": structured,
                                  "usage": {"input_tokens": 2, "cache_creation_input_tokens": 10,
                                            "cache_read_input_tokens": 100, "output_tokens": 7}})])


def test_the_slot_is_a_setting_like_any_other_and_picks_the_harness_by_its_model():
    assert "claude-cli" in settings.APIS["text"] and settings.check_slot("text", SLOT) == []
    assert type(adapters.for_slot("text", None, SLOT)).__name__ == "ClaudeCLI"
    assert slots.pick("text", None, SLOT)[0].id == "claude-opus-5.5"
    assert settings.host_of(CC.WHERE) == "api.anthropic.com"             # where its pages go, for the notices


def test_the_program_is_run_bare_of_the_user_s_own_setup_with_the_harness_s_effort():
    a = CC.ClaudeCLI(model="claude-opus-5-5")
    hp = harnesses.get("claude-opus-5.5")()
    args, stdin, system, dropped = a.request("You work on a page.", [{"role": "user", "text": "hi", "images": [b"png"]}],
                                             tools=TOOLS, force_tool=True, caps={"vision": True, "forced_tool": True},
                                             harness=hp)
    pairs = dict(zip(args, args[1:]))
    assert args[0] == "-p" and pairs["--tools"] == "" and pairs["--setting-sources"] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    assert pairs["--model"] == "claude-opus-5-5" and pairs["--effort"] == "medium"
    schema = json.loads(pairs["--json-schema"])
    calls = schema["properties"]["tool_calls"]
    assert calls["minItems"] == 1 and [c["properties"]["name"]["const"] for c in calls["items"]["anyOf"]] == ["answer", "skip"]
    assert calls["items"]["anyOf"][0]["properties"]["arguments"] == TOOLS[0]["parameters"]
    assert "- answer: Answer in words." in system and system.startswith("You work on a page.")
    sent = json.loads(stdin)["message"]["content"]
    assert [b["type"] for b in sent] == ["image", "text"] and sent[1]["text"] == "hi" and dropped == 0
    # no key, no token, nothing of the sign-in anywhere in what is handed over
    assert a.key is None and "token" not in " ".join(args).lower() and "credential" not in " ".join(args).lower()


def test_no_vision_drops_the_pictures_and_no_effort_is_sent_without_a_harness():
    a = CC.ClaudeCLI(model="opus")
    args, stdin, system, dropped = a.request("", [{"role": "user", "text": "hi", "images": [b"a", b"b"]}], caps={"vision": False})
    assert dropped == 2 and "--effort" not in args and "--json-schema" not in args
    assert [b["type"] for b in json.loads(stdin)["message"]["content"]] == ["text"]


def test_a_conversation_goes_as_blocks_a_later_request_begins_with():
    msgs = [{"role": "user", "text": "Record apple."},
            {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "record", "arguments": {"word": "apple"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "record", "text": "recorded"}]
    first, _ = CC.blocks_of(msgs[:1] + msgs[1:2], True)
    later, _ = CC.blocks_of(msgs, True)
    assert later[:2] == first[:2]                                        # the same blocks, in the same order
    assert later[1]["text"] == '[YOUR EARLIER TURN]\ncalled record({"word": "apple"})'
    assert later[2]["text"] == "[RESULT OF record]\nrecorded" and later[-1]["text"].startswith("[NOW]")


def test_what_the_program_prints_becomes_the_reply(monkeypatch):
    ran = []

    def run(args, stdin=None):
        ran.append(args)
        if args[:2] == ["auth", "status"]:
            return types.SimpleNamespace(returncode=0, stdout='{"loggedIn": true}', stderr="")
        return types.SimpleNamespace(returncode=0, stderr="", stdout=_printed(
            {"text": "", "tool_calls": [{"name": "answer", "arguments": {"lines": ["Lima."]}},
                                        {"name": "not-a-tool", "arguments": {}}]}))
    monkeypatch.setattr(CC, "_run", run)
    a = CC.ClaudeCLI(model="claude-opus-5-5")
    r = a.chat("sys", [{"role": "user", "text": "capital of Peru?"}], tools=TOOLS, force_tool=True, caps={"vision": True})
    assert [(c["name"], c["arguments"]) for c in r["tool_calls"]] == [("answer", {"lines": ["Lima."]})]
    assert r["stop"] == "tool_use" and r["usage"] == {"input": 112, "output": 7, "cached": 100}
    assert r["forced_refused"] is False and r["dropped_images"] == 0
    assert "--system-prompt-file" in ran[0]
    import os
    assert not os.path.exists(ran[0][ran[0].index("--system-prompt-file") + 1])       # the system text's file is gone
    # a plain reply, and an error said as the program said it
    monkeypatch.setattr(CC, "_run", lambda args, stdin=None: types.SimpleNamespace(returncode=0, stderr="", stdout=_printed(text="ready")))
    assert a.chat("sys", [{"role": "user", "text": "say ready"}])["text"] == "ready"
    monkeypatch.setattr(CC, "_run", lambda args, stdin=None: types.SimpleNamespace(returncode=1, stderr="", stdout=_printed(text="usage limit reached", error=True)))
    try:
        a.chat("sys", [{"role": "user", "text": "hi"}])
        raise AssertionError("no error")
    except adapters.AdapterError as ex:
        assert "usage limit reached" in str(ex)


def test_a_schema_too_long_for_a_command_line_goes_loose_with_the_tools_schemas_in_the_system_text():
    big = [{"name": "t%d" % i, "description": "d", "parameters": {"type": "object", "properties": {
        "p%d" % k: {"type": "string", "description": "x" * 200} for k in range(12)}}} for i in range(14)]
    a = CC.ClaudeCLI(model="opus")
    args, stdin, system, dropped = a.request("sys", [{"role": "user", "text": "hi"}], tools=big, caps={"vision": True})
    schema = json.loads(args[args.index("--json-schema") + 1])
    assert schema["properties"]["tool_calls"]["items"]["anyOf"][0]["properties"]["arguments"] == {"type": "object"}
    assert "arguments (JSON schema):" in system
