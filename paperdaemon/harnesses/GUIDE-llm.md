# How to create a new LLM harness

An LLM harness tells PaperDaemon how to work with one text model on one server: what the model is shown and
told, how its replies are read, how it is asked small questions about a page (where something is, what a
picture says), and what it can do. PaperDaemon reads every harness in this folder, checks it, and lists every
one that passes in the Harness box of the Text / Reasoning tab. One that fails is listed with what is wrong with it.

PaperDaemon's own harnesses are part of the app, not kept here: the built-in default, and llama.cpp - Qwen 3.6
27B and llama.cpp - Qwen 3.8 27B. A harness here builds on one of them (`extends`, or the built-in default when
it names none) and changes only what it names.

How the model thinks and how much context it has are the server's own settings, in its start script, never a
harness's.

A harness here is one of three things, from simplest to most powerful:

1. **A `.json` file**: the model's capabilities and values (below).
2. **A skills folder**: a folder with a `harness.json` and a `skills` folder of `.md` files, each replacing
   what the model is told about one job or tool. No code.
3. **A `.py` file**: a Python class that overrides parts of the harness itself.

## Name it for its server and model

A harness is made for one kind of server running one model, and its name says both: `llama.cpp - Qwen 3.8 27B`.
Every harness also says, for the people who read it:

| Field | What it is |
| --- | --- |
| `server` | Required. The server it is made for: `"llama.cpp (llama-server)"`. |
| `models` | Required. The models it is made for: `["Qwen 3.8 27B"]`. |
| `notes` | What anyone choosing it should know: what it was tested with, what it does well, what to avoid. |

PaperDaemon shows these and never acts on them. A harness you build on another still says its own.

A model reached with an API key is named the same way, and its server is the API it is reached through:
`Anthropic API - My model`, with `"server": "Anthropic API (Messages)"` and
`"models": ["my-model"]`; or `OpenAI API - ...`. The same model behind two
different APIs is two harnesses, because each API takes its requests (tool calls, structured output,
pictures) its own way.

## 1. A `.json` harness

| Field | What it is |
| --- | --- |
| `id` | Its name in the settings. Optional: the file name without `.json`. Must not be taken. |
| `name` | What the Harness box shows: the server, then the model. Optional: the `id`. |
| `extends` | The harness it builds on: one of PaperDaemon's, or another here. Optional: the built-in default. |
| `patterns` | Model names (regular expressions) that make this harness the automatic choice. |
| `refuse` | Model names that rule it out even when a pattern matches. |
| `vision` | `true` when the model can see a page picture. |
| `forced_tool` | `true` when the server can force the model to answer with a tool call. |
| `max_output` | The most tokens one answer may have, or `null` for the server's own limit. |
| `brief_additions` | Text added to the instructions PaperDaemon gives the model. |
| `request` | Extra fields for every request, by a capability and its value: `{"vision": {"off": {"cache_prompt": true}}}`. |
| `features` | Things this model should not be asked to do: `{"off": ["chart"]}`. The model is never offered them. |
| `inspect_tokens` | How many tokens the model may spend looking at the page (zooming in, reading its history) before it decides. Optional: 12000. |
| `assists` | Keyword assists for a model that needs help with one decision (see below). Optional: none. |
| `cli` | How a command-line program is spoken to, when the model's source is a command line (see below). Optional: none. |
| `lean` | `true` for a model strong enough to do a whole job from one look at the page, and dear to call (see below). Optional: `false`. |
| `offered` | `false` for a harness that only holds what others share, such as a program's `cli`: it is not listed in the Harness box. Optional: `true`. |

A model that sees pictures, is matched by name, and is never asked to draw:

```json
{
  "id": "my-model",
  "name": "llama.cpp - My model 14B",
  "server": "llama.cpp (llama-server)",
  "models": ["My model 14B"],
  "notes": "Tested on the benchmark jobs with thinking off. It draws poorly, so drawing is off.",
  "patterns": ["my-model"],
  "vision": true,
  "forced_tool": true,
  "features": {"off": ["draw"]}
}
```

Save it here as `my-model.json`, then choose it in the Text / Reasoning tab's Harness box, or leave the box empty and
let the pattern pick it.

### The lean way

PaperDaemon's own "Lean Default (stronger models only)" has `lean: true`, and its harnesses for Claude Opus 5.5,
Sonnet 5.5 and Haiku 5.5 build on it. Extend it (`"extends": "lean-default"`) for any other strong model. A lean
lineup is worked with far fewer tokens: a short job description; each turn sent only the calls it may make, not the
whole tool list; a page of typed text sent as its text, with no picture; and a job's words or sketch given in the
plan itself, so most jobs are one call. A sketch is not shown back to the model for a fix, which would be a call more. Every rule PaperDaemon enforces is checked all the same. A weaker model on a
lean harness plans badly: leave those on the built-in default.

### A command-line program

A lineup's text model can be a command: Source "Command line", then the WHOLE command as you would type it in a
terminal, your own arguments included: `my-program --model big-one --effort high`. There is no other field: which
model and how much effort are the command's to say, in the program's own way. PaperDaemon starts the program itself
(no shell), once for each turn, hands it the request and reads what it prints. With no harness for the
program, the system text and the conversation go on its input and what it prints is the answer. A program that wants
more than that gets a harness with a `cli` field, which says how it is spoken to:

| In `cli` | What it is |
| --- | --- |
| `program` | The program's usual name. A command that runs this program uses this harness's `cli`, whatever model it names. |
| `places` | Where the program is installed, tried when the command is not on the PATH. `~` and `%NAMES%` are filled in. |
| `args` | What is added after the user's own arguments for every request (see the placeholders): only what carries the request in and the answer out, never a model or an effort. A list inside the list is left out whole when a placeholder in it has nothing to give, and when it begins with an argument the command itself already gives: with the command `my-program --effort high`, a `["--effort", ...]` list is left out and the typed effort stands. `{"each_picture": [...]}` is repeated for every picture. |
| `input` | What goes on the program's input: text with placeholders, or `{"json": ..., "text": ..., "picture": ...}`, a JSON value written on one line in which `"{parts}"` becomes the list of the conversation's turns, each written as `text` says and each picture as `picture` says. Optional: the system text, then the conversation. |
| `output` | Where the answer is in what the program prints: `format` (`text`, `json`, or `json-lines` with `where`, the fields of the line to read), `text` (the answer's words), `answer` (a structured answer the program checked against the schema), `error` and `error_text`, `usage` (`input`, `output`, `cached`). Each is a dotted path such as `usage.output_tokens`; a count may be a list of paths added up. Optional: what it prints is the answer. |
| `ready` | `{"args": [...], "json": "a.path", "else": "what to tell the user"}`: a run of the program that says whether it is ready (signed in). Optional: a program that is found is ready. |
| `sends_to` | The host the program sends a page to, for the notice that pages leave this computer. Optional: they stay here. |
| `answer_rule` | One sentence on how this program wants a structured answer given. Optional. |
| `model_arg` | The argument after which a command names its model (`--model`). Nothing is added for it: it lets PaperDaemon read the model out of the command, to pick that model's harness. Optional. |

Placeholders: `{system}` or `{system_file}` (the system text, or a file holding it); `{prompt}` or
`{prompt_file}` (the conversation as plain text); `{schema}` or `{schema_file}` (the tools as one JSON schema for the
answer); `{picture_file}`, and in `input`'s `picture` also `{base64}` and `{media_type}`; `{text}` in `input`'s
`text`; and `{request.a.b}`, any field of the request as this harness's `request` tuned it, such as an effort.
Files are made in a folder of the run's own and removed after it.

A program that takes its prompt on its input and a picture as a file:

```json
{
  "id": "my-program",
  "name": "my-program (command line)",
  "server": "my-program, a command-line program",
  "models": ["The models it takes by name"],
  "notes": "Prompt on the input, one --image for each picture, plain text out.",
  "offered": false,
  "vision": true,
  "cli": {
    "program": "my-program",
    "model_arg": "--model",
    "args": [["--system", "{system_file}"], {"each_picture": ["--image", "{picture_file}"]}],
    "input": "{prompt}"
  }
}
```

PaperDaemon's own `claude-code` harness is a fuller one: a JSON message on the input with pictures in it, the answer
read from the last result line of what the program prints, a readiness check, and where pages go. A program that
checks an answer against a schema can be handed it (`["--its-argument", "{schema}"]`), but look at what that costs:
`claude` makes a second request for every answer checked that way, so its data leaves the checking to PaperDaemon.

### Keyword assists

An assist acts after the model has decided, never in place of it. It reads one piece of the decision, fires on
whole keywords (case ignored) or on how the text ends, and then either tells the model something once (`hint`:
the model decides again, and its answer stands) or changes the value (`set`: the job's record names the assist
that did it).

| Field | What it is |
| --- | --- |
| `decision` | What it helps with: `step.kind`, `step.replaces`, `item.ruling`, `markup.target`, `posts.source` or `image.steps`. |
| `reads` | The text it looks at: `step.what`, `step.words`, `step.source`, `step.search` or `item.text`. |
| `keywords` or `ends_with` | What fires it: a list of words, or the text's last characters. |
| `when` | Optional: fire only when the model chose this value (a step's kind, a ruling's `then`). |
| `hint` or `set` | One of them: what to tell the model, or the fields to set. |

A model that keeps painting a picture when the page asks for one from the web:

```json
"assists": [
  {"decision": "step.kind", "reads": "step.what", "when": "image",
   "keywords": ["the web", "online", "real photo"],
   "hint": "A picture that already exists is a web_picture step; image paints a new one."}
]
```

A whole harness of them is in PaperDaemon's source, `paperdaemon/harnesses/examples/keyword-assists.json`. It
is never used on its own: copy it into this folder to use it.

## 2. A skills folder

```
plain-words\
  harness.json        the same fields as a .json harness; its id is the folder's name unless it says one
  skills\
    write.md          what the model is told about writing, word for word
```

Each `.md` file in `skills` replaces the skill of that name; everything else stays as the harness it builds on.

## 3. A `.py` harness

A `.py` file defines one class that builds on a harness and overrides only the methods it changes:

```python
from paperdaemon import harnesses


class MyModel(harnesses.get("qwen3.8-27b")):
    id = "my-model"
    name = "llama.cpp - My model 14B"
    server = "llama.cpp (llama-server)"
    models = ["My model 14B"]
    notes = "Answers in JSON prose instead of tool calls."

    def calls(self, message):
        """Read the calls out of the model's prose."""
        ...
```

What a harness can override:

| Method | What it decides |
| --- | --- |
| `intake(host, doc, page, name, wake)` | The first turn's messages: what the model is shown and told. |
| `decision(host, msgs)` | The turn that decides: which calls may answer it, how it is asked. |
| `calls(message)`, `read_call(call, cut)` | How a reply's calls are found and read. |
| `nudge_no_call`, `nudge_runaway`, `nudge_refused`, `nudge_gathered` | What goes back when a reply missed. |
| `outcome(fn, args, result)` | What the decision means: jobs, a skip, or a finished page (`harnesses.text.FinishedPage`). |
| `locate_many`, `read_located`, `locate_one`, `read_located_one` | How the model is asked where things are, and how its answer reads. |
| `ask(host, content, max_tokens, temperature)` | The request for a plain reply (a game's line, a reading of a picture). |
| `describe(host, path)` | A picture in words, for a model that cannot see. |
| `validate(host, staged)` | Extra refusals before commit (PaperDaemon's own checks always run too). |
| `conflict(host, yours, ours, made_by)` | How a conflict between the tablet and a job is put to the model. |
| `kinds`, `provides` | The job kinds it supports, and abilities its model provides itself (`"pictures"`, `"search"`). |

A harness builds turns and reads replies; PaperDaemon sends them, and only PaperDaemon writes your pages. A
harness can import anything Python itself ships.
