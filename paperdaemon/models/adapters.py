"""Speaking each API family: OpenAI-compatible chat, Anthropic Messages, the Stable Diffusion web UI API
and the OpenAI Images API.

Every adapter takes and returns one neutral shape, so the host never sees an API's own format:

    messages  [{"role": "user", "text": str, "images": [png bytes, ...]},
               {"role": "assistant", "text": str, "tool_calls": [{"id", "name", "arguments": dict}]},
               {"role": "tool", "tool_call_id": str, "name": str, "text": str}]
    tools     [{"name", "description", "parameters": JSON schema}]
    reply     {"text", "tool_calls", "stop", "usage": {"input", "output"}, "dropped_images",
               "forced_refused"}

A text slot whose vision is off never receives an image: the adapter drops it and counts it, so a host
mistake cannot leak a page to a model that cannot use it.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from .. import vault
from . import slots

LIST_TIMEOUT = 5            # listing models or checking health: a live server answers at once
# A model call (a completion, a picture) takes as long as the model needs: no timeout. Listing models and
# checking health are not model calls and keep LIST_TIMEOUT.
MODEL_CALL = None


class AdapterError(Exception):
    def __init__(self, message, status=None, body=""):
        super().__init__(message)
        self.status = status
        self.body = body


def _where(url):
    p = urllib.parse.urlsplit(url)
    return p.netloc or url


def _request(method, url, body=None, headers=None, timeout=LIST_TIMEOUT, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
    except urllib.error.HTTPError as ex:
        text = ex.read().decode("utf-8", "replace")[:600]
        raise AdapterError("%s answered %d" % (_where(url), ex.code), ex.code, text)
    except (urllib.error.URLError, OSError) as ex:
        reason = getattr(ex, "reason", ex)
        raise AdapterError("%s did not answer (%s)" % (_where(url), reason))
    if raw:
        return payload
    try:
        return json.loads(payload)
    except ValueError:
        raise AdapterError("%s answered with something that is not JSON" % _where(url))


def _b64(png):
    return base64.b64encode(png).decode("ascii")


def _strip_v1(url):
    url = (url or "").rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def api_base(url):
    """Where a location's API routes live: a server's own address (http://host:port, an API's site) has them under
    /v1; a location that names a path IS its API's base -- one ending in /v1, or another, such as Google's
    https://generativelanguage.googleapis.com/v1beta/openai, whose chat route is /v1beta/openai/chat/completions."""
    from urllib.parse import urlparse
    url = (url or "").rstrip("/")
    return url + "/v1" if urlparse(url).path in ("", "/") else url


class Adapter:
    family = ""

    def __init__(self, url, key=None, model=""):
        self.base = _strip_v1(url)
        self.api = api_base(url)          # the /v1 routes (models, chat, messages, images); base is the server's root
        self.key = key or None
        self.model = model or ""

    def headers(self):
        return {}

    def models(self):
        return []

    def health(self):
        """True when the server answers and is ready for work."""
        try:
            self.models()
            return True
        except AdapterError:
            return False


# ---------------------------------------------------------------- text

class OpenAIChat(Adapter):
    """Chat Completions: llama.cpp's server, vLLM, Ollama's /v1, LM Studio, OpenAI and compatible hosts."""
    family = "openai"

    def headers(self):
        return {"Authorization": "Bearer " + self.key} if self.key else {}

    def models(self):
        d = _request("GET", self.api + "/models", headers=self.headers())
        return [m.get("id") for m in d.get("data") or [] if m.get("id")]

    def health(self):
        try:
            _request("GET", self.base + "/health", headers=self.headers())
            return True                              # llama.cpp: 200 once the model is loaded
        except AdapterError as ex:
            if ex.status == 503:                     # llama.cpp while loading
                return False
        return super().health()

    def request(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
                temperature=None, max_tokens=None):
        caps = caps or {}
        vision = bool(caps.get("vision"))
        out, dropped = ([{"role": "system", "content": system}] if system else []), 0
        for m in messages:
            role = m["role"]
            if role == "user":
                imgs = list(m.get("images") or [])
                if imgs and not vision:
                    dropped, imgs = dropped + len(imgs), []
                if imgs:
                    parts = [{"type": "text", "text": m.get("text") or ""}]
                    parts += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + _b64(i)}}
                              for i in imgs]
                    out.append({"role": "user", "content": parts})
                else:
                    out.append({"role": "user", "content": m.get("text") or ""})
            elif role == "assistant":
                a = {"role": "assistant", "content": m.get("text") or ""}
                if m.get("tool_calls"):
                    a["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"],
                                                     "arguments": json.dumps(c.get("arguments") or {})}}
                                       for c in m["tool_calls"]]
                out.append(a)
            elif role == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m.get("text") or ""})
        body = {"messages": out}
        if self.model:
            body["model"] = self.model
        if tools:
            body["tools"] = [{"type": "function",
                              "function": {"name": t["name"], "description": t.get("description") or "",
                                           "parameters": t.get("parameters") or {"type": "object", "properties": {}}}}
                             for t in tools]
            body["tool_choice"] = "required" if (force_tool and caps.get("forced_tool")) else "auto"
        if temperature is not None:
            body["temperature"] = float(temperature)
        limit = max_tokens or caps.get("max_output")
        if limit:
            body["max_tokens"] = int(limit)
        if harness is not None:
            body = harness.tune(body, caps)
        return body, dropped

    @staticmethod
    def parse(d):
        choice = (d.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            f = c.get("function") or {}
            args = f.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except ValueError:
                    args = {"_unparsed": args}
            calls.append({"id": c.get("id") or "", "name": f.get("name") or "", "arguments": args or {}})
        u = d.get("usage") or {}
        return {"text": msg.get("content") or "", "tool_calls": calls, "stop": choice.get("finish_reason") or "",
                "usage": {"input": u.get("prompt_tokens"), "output": u.get("completion_tokens")}}

    def chat(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
             temperature=None, max_tokens=None):
        body, dropped = self.request(system, messages, tools, force_tool, caps, harness, temperature, max_tokens)
        refused = False
        try:
            d = _request("POST", self.api + "/chat/completions", body, self.headers(), MODEL_CALL)
        except AdapterError as ex:
            # a server that cannot force a tool call says so with a 400 naming tool_choice
            if ex.status == 400 and body.get("tool_choice") == "required" and "tool_choice" in ex.body:
                body["tool_choice"], refused = "auto", True
                d = _request("POST", self.api + "/chat/completions", body, self.headers(), MODEL_CALL)
            else:
                raise
        r = self.parse(d)
        r["dropped_images"], r["forced_refused"] = dropped, refused
        return r


class AnthropicChat(Adapter):
    """The Anthropic Messages API."""
    family = "anthropic"
    VERSION = "2023-06-01"

    def __init__(self, url, key=None, model=""):
        super().__init__(url or "https://api.anthropic.com", key, model)

    def headers(self):
        h = {"anthropic-version": self.VERSION}
        if self.key:
            h["x-api-key"] = self.key
        return h

    def models(self):
        d = _request("GET", self.api + "/models", headers=self.headers())
        return [m.get("id") for m in d.get("data") or [] if m.get("id")]

    def request(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
                temperature=None, max_tokens=None):
        caps = caps or {}
        vision = bool(caps.get("vision"))
        out, dropped = [], 0
        for m in messages:
            role = m["role"]
            if role == "user":
                imgs = list(m.get("images") or [])
                if imgs and not vision:
                    dropped, imgs = dropped + len(imgs), []
                blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _b64(i)}}
                          for i in imgs]
                blocks.append({"type": "text", "text": m.get("text") or ""})
                out.append({"role": "user", "content": blocks})
            elif role == "assistant":
                blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("arguments") or {}}
                           for c in m.get("tool_calls") or []]
                out.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                result = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m.get("text") or ""}
                last = out[-1] if out else None
                # consecutive tool results travel in one user message
                if last and last["role"] == "user" and all(b.get("type") == "tool_result" for b in last["content"]):
                    last["content"].append(result)
                else:
                    out.append({"role": "user", "content": [result]})
        body = {"model": self.model, "max_tokens": int(max_tokens or caps.get("max_output") or 4096),
                "messages": out}
        if system:
            body["system"] = system
        thinking = False                         # thinking is the model's and its server's own setting
        if tools:
            body["tools"] = [{"name": t["name"], "description": t.get("description") or "",
                              "input_schema": t.get("parameters") or {"type": "object", "properties": {}}}
                             for t in tools]
            # forcing a tool is not allowed together with thinking
            forced = force_tool and caps.get("forced_tool") and not thinking
            body["tool_choice"] = {"type": "any"} if forced else {"type": "auto"}
        if temperature is not None and not thinking:
            body["temperature"] = float(temperature)
        if harness is not None:
            body = harness.tune(body, caps)
        return body, dropped

    @staticmethod
    def parse(d):
        blocks = d.get("content") or []
        text = "".join(b.get("text") or "" for b in blocks if b.get("type") == "text")
        calls = [{"id": b.get("id") or "", "name": b.get("name") or "", "arguments": b.get("input") or {}}
                 for b in blocks if b.get("type") == "tool_use"]
        u = d.get("usage") or {}
        return {"text": text, "tool_calls": calls, "stop": d.get("stop_reason") or "",
                "usage": {"input": u.get("input_tokens"), "output": u.get("output_tokens")}}

    def chat(self, system, messages, tools=(), force_tool=False, caps=None, harness=None,
             temperature=None, max_tokens=None):
        body, dropped = self.request(system, messages, tools, force_tool, caps, harness, temperature, max_tokens)
        refused = False
        try:
            d = _request("POST", self.api + "/messages", body, self.headers(), MODEL_CALL)
        except AdapterError as ex:
            if ex.status == 400 and body.get("tool_choice", {}).get("type") == "any" and "tool_choice" in ex.body:
                body["tool_choice"], refused = {"type": "auto"}, True
                d = _request("POST", self.api + "/messages", body, self.headers(), MODEL_CALL)
            else:
                raise
        r = self.parse(d)
        r["dropped_images"], r["forced_refused"] = dropped, refused
        return r


# ---------------------------------------------------------------- the host's requests, for any API family

def from_openai(body):
    """An OpenAI-format chat request (what the host sends) -> keyword arguments for an adapter's chat():
    system, messages and tools in the neutral shape, force_tool, temperature, max_tokens."""
    system, messages = [], []
    for m in body.get("messages") or []:
        role, content = m.get("role"), m.get("content")
        parts = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
        text = "\n".join(p.get("text") or "" for p in parts if p.get("type") == "text")
        images = []
        for p in parts:
            url = (p.get("image_url") or {}).get("url") if p.get("type") == "image_url" else None
            if url and url.startswith("data:") and "," in url:
                images.append(base64.b64decode(url.split(",", 1)[1]))
        if role == "system":
            system.append(text)
        elif role == "tool":
            messages.append({"role": "tool", "tool_call_id": m.get("tool_call_id"), "name": m.get("name") or "",
                             "text": text})
        elif role == "assistant":
            calls = []
            for c in m.get("tool_calls") or []:
                f = c.get("function") or {}
                try:
                    args = json.loads(f.get("arguments") or "{}")
                except ValueError:
                    args = {}
                calls.append({"id": c.get("id"), "name": f.get("name"), "arguments": args})
            messages.append({"role": "assistant", "text": text, "tool_calls": calls})
        else:
            messages.append({"role": "user", "text": text, "images": images})
    tools = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
              "parameters": t["function"].get("parameters") or {"type": "object", "properties": {}}}
             for t in body.get("tools") or [] if t.get("function")]
    return {"system": "\n\n".join(system), "messages": messages, "tools": tools,
            "force_tool": body.get("tool_choice") == "required" and bool(tools),
            "temperature": body.get("temperature"), "max_tokens": body.get("max_tokens")}


def openai_stream(reply):
    """A neutral reply as an OpenAI-format stream (server-sent events), the shape the host reads."""
    delta = {"role": "assistant", "content": reply.get("text") or ""}
    if reply.get("tool_calls"):
        delta["tool_calls"] = [{"index": i, "id": c.get("id") or "call_%d" % i, "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {})}}
                               for i, c in enumerate(reply["tool_calls"])]
    stop = {"tool_use": "tool_calls", "end_turn": "stop", "max_tokens": "length"}.get(reply.get("stop"), reply.get("stop"))
    usage = reply.get("usage") or {}
    events = [{"choices": [{"index": 0, "delta": delta, "finish_reason": stop or "stop"}]},
              {"choices": [], "usage": {"prompt_tokens": usage.get("input"), "completion_tokens": usage.get("output")}}]
    return b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"


# ---------------------------------------------------------------- image

class SDAPI(Adapter):
    """The Stable Diffusion web UI API: stable-diffusion.cpp's server, Forge, AUTOMATIC1111."""
    family = "sdapi"

    def models(self):
        d = _request("GET", self.base + "/sdapi/v1/sd-models")
        return [m.get("model_name") or m.get("title") or m.get("name") for m in (d or []) if isinstance(m, dict)]

    def health(self):
        for route in ("/sdapi/v1/sd-models", "/sdapi/v1/samplers"):
            try:
                _request("GET", self.base + route)
                return True
            except AdapterError as ex:
                if ex.status != 404:
                    return False
        return False

    @staticmethod
    def request(prompt, width, height, steps, cfg, sampler, scheduler=None, seed=-1, shift=None):
        if shift is not None:
            # stable-diffusion.cpp's server takes a per-render flow shift only through this block, which
            # it lifts out of the prompt before the text encoder sees it
            prompt += " <sd_cpp_extra_args>%s</sd_cpp_extra_args>" % json.dumps({"sample_params": {"flow_shift": shift}})
        body = {"prompt": prompt, "steps": int(steps), "cfg_scale": float(cfg), "width": int(width),
                "height": int(height), "sampler_name": sampler, "batch_size": 1, "seed": int(seed)}
        if scheduler:
            body["scheduler"] = scheduler
        return body

    def generate(self, prompt, width, height, steps, cfg, sampler, scheduler=None, seed=-1, shift=None):
        body = self.request(prompt, width, height, steps, cfg, sampler, scheduler, seed, shift)
        d = _request("POST", self.base + "/sdapi/v1/txt2img", body, timeout=MODEL_CALL)
        imgs = d.get("images") or []
        if not imgs:
            raise AdapterError("%s returned no image" % _where(self.base))
        return base64.b64decode(imgs[0].split(",", 1)[-1])


class OpenAIImages(Adapter):
    """The OpenAI Images API and hosts compatible with it."""
    family = "openai-images"

    def headers(self):
        return {"Authorization": "Bearer " + self.key} if self.key else {}

    def models(self):
        d = _request("GET", self.api + "/models", headers=self.headers())
        return [m.get("id") for m in d.get("data") or [] if m.get("id")]

    def request(self, prompt, width, height, **_):
        body = {"prompt": prompt, "n": 1, "size": "%dx%d" % (int(width), int(height))}
        if self.model:
            body["model"] = self.model
        return body

    def generate(self, prompt, width, height, steps=None, cfg=None, sampler=None, scheduler=None, seed=-1,
                 shift=None):
        d = _request("POST", self.api + "/images/generations", self.request(prompt, width, height),
                     self.headers(), MODEL_CALL)
        item = (d.get("data") or [{}])[0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return _request("GET", item["url"], timeout=MODEL_CALL, raw=True)
        raise AdapterError("%s returned no image" % _where(self.base))


CHAT = {"openai": OpenAIChat, "anthropic": AnthropicChat}
IMAGE = {"sdapi": SDAPI, "openai-images": OpenAIImages}


def for_slot(role, s=None, m=None):
    """The adapter for a slot as configured, with its key from the credential store."""
    m = m if m is not None else slots.slot(role, s)
    cls = (CHAT if role == "text" else IMAGE)[m.get("api") or ("openai" if role == "text" else "sdapi")]
    return cls(m.get("location") or "", vault.get(slots.key_of(role, m)), m.get("model") or "")
