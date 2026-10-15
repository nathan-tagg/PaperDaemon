import json

from paperdaemon.models import adapters
from paperdaemon.models.checks import square_png
from paperdaemon import harnesses

PNG = square_png((255, 0, 0), 8)
TOOLS = [{"name": "plan", "description": "Plan the page.",
          "parameters": {"type": "object", "properties": {"what": {"type": "string"}}, "required": ["what"]}}]
CHAT = [{"role": "user", "text": "look", "images": [PNG]},
        {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "plan", "arguments": {"what": "x"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "plan", "text": "ok"},
        {"role": "tool", "tool_call_id": "c2", "name": "plan", "text": "ok too"}]


def test_openai_request_shape():
    a = adapters.OpenAIChat("http://127.0.0.1:11434/v1", model="m")
    body, dropped = a.request("sys", CHAT, TOOLS, force_tool=True, caps={"vision": True, "forced_tool": True},
                              temperature=0.3)
    assert a.base == "http://127.0.0.1:11434"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    parts = body["messages"][1]["content"]
    assert parts[0]["type"] == "text" and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == json.dumps({"what": "x"})
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}
    assert body["tool_choice"] == "required" and body["tools"][0]["function"]["name"] == "plan"
    assert body["temperature"] == 0.3 and dropped == 0


def test_no_image_reaches_a_model_that_cannot_see():
    a = adapters.OpenAIChat("http://127.0.0.1:11434")
    body, dropped = a.request("", CHAT[:1], caps={"vision": False})
    assert dropped == 1 and body["messages"][0]["content"] == "look"
    b = adapters.AnthropicChat("", key="k", model="m")
    body, dropped = b.request("", CHAT[:1], caps={"vision": False})
    assert dropped == 1 and all(block["type"] != "image" for block in body["messages"][0]["content"])


def test_forcing_needs_the_capability():
    a = adapters.OpenAIChat("http://x")
    body, _ = a.request("", CHAT[:1], TOOLS, force_tool=True, caps={"forced_tool": False})
    assert body["tool_choice"] == "auto"


def test_thinking_is_the_servers_own_setting_never_the_request():
    a = adapters.OpenAIChat("http://x")
    body, _ = a.request("", CHAT[:1], caps={}, harness=harnesses.get("qwen3.6-27b")())
    assert "chat_template_kwargs" not in body


def test_openai_parse():
    r = adapters.OpenAIChat.parse({"choices": [{"finish_reason": "tool_calls", "message": {
        "content": None, "tool_calls": [{"id": "a", "function": {"name": "plan", "arguments": "{\"what\": \"y\"}"}}]}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3}})
    assert r["tool_calls"] == [{"id": "a", "name": "plan", "arguments": {"what": "y"}}]
    assert r["text"] == "" and r["usage"] == {"input": 10, "output": 3}


def test_anthropic_request_shape():
    a = adapters.AnthropicChat("https://api.anthropic.com/v1", key="k", model="claude-x")
    body, _ = a.request("sys", CHAT, TOOLS, force_tool=True, caps={"vision": True, "forced_tool": True},
                        temperature=0.3)
    assert a.base == "https://api.anthropic.com"
    assert body["system"] == "sys" and body["max_tokens"] == 4096
    user = body["messages"][0]["content"]
    assert user[0]["type"] == "image" and user[0]["source"]["media_type"] == "image/png" and user[-1]["type"] == "text"
    assert body["messages"][1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "plan", "input": {"what": "x"}}
    results = body["messages"][2]["content"]          # consecutive tool results travel together
    assert [r["tool_use_id"] for r in results] == ["c1", "c2"] and len(body["messages"]) == 3
    assert body["tool_choice"] == {"type": "any"} and body["tools"][0]["input_schema"]["required"] == ["what"]


def test_anthropic_requests_carry_no_thinking_and_can_force_a_tool():
    a = adapters.AnthropicChat("", key="k", model="m")
    body, _ = a.request("", CHAT[:1], TOOLS, force_tool=True, caps={"forced_tool": True}, temperature=0.3)
    assert body["tool_choice"] == {"type": "any"} and body["temperature"] == 0.3
    assert "thinking" not in body


def test_anthropic_parse():
    r = adapters.AnthropicChat.parse({"content": [{"type": "text", "text": "hi"},
                                                  {"type": "tool_use", "id": "t", "name": "plan", "input": {"what": 1}}],
                                      "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 2}})
    assert r["text"] == "hi" and r["tool_calls"][0]["arguments"] == {"what": 1} and r["stop"] == "tool_use"


def test_sdapi_request_and_flow_shift():
    body = adapters.SDAPI.request("a fox", 1024, 1024, 4, 1.0, "euler", None, 7, shift=2.5)
    assert body["prompt"].startswith("a fox <sd_cpp_extra_args>")
    assert json.loads(body["prompt"].split("<sd_cpp_extra_args>")[1].split("</")[0]) == {"sample_params": {"flow_shift": 2.5}}
    assert body["steps"] == 4 and body["cfg_scale"] == 1.0 and body["seed"] == 7 and "scheduler" not in body
    assert adapters.SDAPI.request("x", 512, 512, 8, 1, "euler", "beta")["scheduler"] == "beta"


def test_openai_images_request():
    a = adapters.OpenAIImages("https://api.example.com/v1", key="k", model="img-1")
    assert a.request("a fox", 1024, 1536) == {"prompt": "a fox", "n": 1, "size": "1024x1536", "model": "img-1"}


def test_errors_never_carry_the_key():
    a = adapters.OpenAIChat("http://127.0.0.1:9", key="sk-secret-value-123456")
    try:
        a.models()
    except adapters.AdapterError as ex:
        assert "sk-secret" not in str(ex)
    else:
        raise AssertionError("port 9 answered")
