# Design

## Context

See proposal.md for why. In the pipeline the model differences were spread through the host as environment
switches (`RM_LLM_VISION`, `RM_LLM_NOTHINK`), family checks (`COLORING_STEPS = {"klein": 12}`) and a
studio registry of launch arguments per model. They worked for one machine and two model families.
PaperDaemon turns them into three separate things, each with one owner:

| Difference | Belongs to | Example |
|---|---|---|
| What a model can do and how it wants to be asked | **harness** (per model family) | Qwen 3.6 27B sees images; Klein wants 4 to 12 steps |
| How a server's API is spoken | **adapter** (per API family) | OpenAI-compatible vs Anthropic tool calls |
| How this machine starts a server | **slot** (per machine, in settings) | the launch script with the model file's path |

## Goals / Non-Goals

**Goals:**
- Any model runs, on the base harness if nothing better is known.
- A harness is a small Python file anyone can read and add.
- Hot swapping reaches parity with the pipeline's studio for a 24 GB card.

**Non-Goals:**
- Automatic VRAM arithmetic. The user decides whether two servers fit by turning hot swapping on or off.
- Managing model downloads. The user installs servers and model files.

## Decisions

**Harnesses are Python classes on a small base interface.** `TextHarness` and `ImageHarness` in
`paperdaemon/harnesses/base.py` carry the capability fields and a few hooks:

- text: `vision`, `forced_tool` (the endpoint can be made to call a tool), `thinking` ("off" or "on"),
  `context` (tokens the host may fill), `max_output` (tokens per turn, or none), and the hooks
  `brief_additions()` (lines appended to the base brief) and `tune(request)` (last-mile request edits,
  such as sampling settings or `chat_template_kwargs`).
- image: `steps`, `steps_range`, `cfg`, `sampler`, `scheduler`, `shift`, `size`, `size_multiple`, its
  `abilities`, and its `workflows`: named recipes (a prompt template with `{subject}`, the steps it needs,
  optional LoRAs applied per request, whether it starts from a reference picture). The coloring page is
  the workflow `childrensColoringBook`; the host asks for it by name and the engine applies the active
  image harness's wording and steps (Klein: the pipeline's coloring prompt and 12 steps; Z-Image: the
  subject first, then the style). The text harness's brief lists the image harness's abilities and
  workflows.

Every field has the base harness's value unless a harness overrides it, so a harness names only what
differs. A text harness also carries the protocols below; `brief_additions()` lets a harness add lines
to the base intake without writing an intake of its own. *Alternative:* harnesses as YAML data. Rejected because two hooks (`tune`, `prompt`) are code in
all but name, and a data format with escape hatches becomes a worse Python.

**A text harness is a set of protocols; the host knows its job from them** (the maintainer's decisions,
2026-09-26 and 2026-09-27). A text harness defines:

- **`intake(job)`, the intake protocol:** what the model is shown and told. It picks from the host's
  readings of the page and builds the model's instructions (the skill) and the tasks on offer, with
  the notebook's prompt word for word.
- **`output(reply, job)`, the output protocol:** what the model's reply means. It returns one of:
  - tasks for the host
  - a finished working copy of the page, with the erasures it made
  - a request for another turn
  - a skip with its reason
- **`tasks`, a protocol per task:** a mapping from each task kind in the host's vocabulary (words, a
  chart, a picture, a coloring page, a mark-up, an erasure, a search or fetch, a tag, a notepad line)
  to its protocol:
  - whether the model is offered the task
  - what the model supplies for it
  - what the host does (place and draw, run and return, or nothing beyond checking)
  - whether the result goes back to the model for another turn
- **`validate(result, job)`:** the checks before commit. What it refuses is how far the harness trusts
  its model; the base harness's checks are the spec's list.

**The host owns everything the protocols hand it:**
- receiving the job and reading the page into readings
- the task vocabulary, and its part of each task: search, fetch, charts, pictures through the image
  slot, decomposing, placing, erasing, tagging, the notepad
- hot swapping between the slots, and stopping runaway turns
- the snapshot, the commit, the mirror, and talking to the daemon

A harness never writes to the mirror or the cloud itself.

**The base harness's protocols are the pipeline's flow.** One decision turn with the plan tool (asked for,
not forced), every task's mechanics and placement left to the host, and a second turn only when a
lookup's results need words. The Qwen 3.6 27B harness keeps that flow and forces the tool call. The
host doing the drawing is what those two harnesses' task protocols say, not a law of the host. A
stronger model's harness can plan over several turns, call the host's tasks as tools mid-turn, draw
for itself, or hand back the whole finished page, and the host follows whichever the protocols say.

The alternative was harnesses that only tune a host-defined flow. That would have tied every model to a
flow built around the weakest one.

**User harnesses load from the data folder.** PaperDaemon imports every `.py` file in
`<data folder>/harnesses/` alongside the shipped ones. A class that satisfies the interface appears under
its declared `name`. An import error is caught, listed on the models screen with the file and the
error, and skipped. The maintainer wants this open: a harness is the user's own code on the user's own
machine.

**Best guess, then the user's pick.** The guess tries three hints in order of how deliberate they are:
the model name the user typed, the model the server reports (`/v1/models`, `/sdapi/v1/sd-models`), and
the model file named in the launch script. A harness matches with a regular expression over those
hints, normalized to lowercase with separators collapsed, so `Qwen3.6-27B`, `qwen3.6-27b-Q8_0.gguf`
and `Qwen_Qwen3.6-27B` all match. Quantization never enters the pattern. The Klein
harness refuses a hint holding a standalone `base` token, because the undistilled Klein base model needs
different steps and guidance. *Alternative:* ask the server which model it runs and trust the answer.
Servers report aliases, file names or nothing, so the answer is a hint, never proof.

**Capabilities resolve in layers.** Effective value = user override, else accepted test result, else
harness value, else base value. The screen shows the value and its layer. The test never changes a
setting by itself; it suggests, and the user accepts.

**Adapters per API family.** `paperdaemon/models/adapters.py` has one class per family with the same small
surface: `chat(system, messages, tools, force_tool)` returning text and tool calls in one normalized
shape, `generate(prompt, **params)` returning PNG bytes, and `probe()` for the test. Forcing a tool call
maps to `tool_choice: "required"` (OpenAI-compatible) or `{"type": "any"}` (Anthropic). Some Anthropic
models refuse a forced tool call, so `forced_tool` is a capability the test can check rather than an
adapter assumption. Images go as `image_url` data URLs (OpenAI-compatible) or `image` blocks with base64
sources (Anthropic). The Stable Diffusion web UI adapter sends `sampler_name`, `scheduler`, `cfg_scale`,
`steps`, `seed`, `width` and `height`; for sd.cpp's server a flow shift rides in the prompt as an
`<sd_cpp_extra_args>` block, which the server lifts out before the text encoder sees it.

**Launch scripts belong to the slot, not the harness.** The maintainer floated a "batch harness" paired with
a "host harness". A harness is shared code about a model family; a launch script holds this machine's
paths, flags and card. Keeping the script in the slot's settings means a harness can ship in the
repository while each user's script stays theirs. The UI still shows them side by side in the slot's
panel, so to the user they read as one thing.

**Hot swap owns its processes by identity.** PaperDaemon writes the script to its data folder
(`launch/text.cmd`, `launch/image.cmd`, or `.sh` elsewhere) and starts it in a new, hidden console. On
Windows the process joins a Job Object created with kill-on-close, so the server and its children end
when PaperDaemon ends, even on a crash; elsewhere it starts in its own process group. Stopping ends that job
object or process group and nothing else. There is no stop script (the maintainer's decision): the start scripts do any other stopping. Readiness is the family's health route answering (`/health`,
`/v1/models` or `/sdapi/v1/sd-models`); the wait ends when the server answers or its process exits,
never on a clock. The UI shows how long it has been loading.

**The text server is the resident one.** Every job starts with a text turn, so after a job that swapped
the image server in, PaperDaemon swaps back straight away rather than at the start of the next job.

**The model's picture steps are clamped; the user's are not.** A harness's `steps_range` bounds what the
model chooses on its own. Numbers the user wrote on the page pass through (the pipeline rendered the user's
own 36 steps on Klein). The host tells the two apart the way the tag step checks direction: a step count
is the user's when that number appears in the notebook's prompt, the typed text or the read handwriting.
The pipeline itself clamped only to 1 to 150 and left the 4 to 12 range to the brief; the check makes the range
hold without overriding the user. The server's own limits still apply.

## Risks / Trade-offs

- [A launch script is arbitrary code run on the user's machine] → It is the user's own text, shown in
  full, edited only by the user; the API that saves it needs the pairing token like every other route.
- [A best guess picks the wrong harness] → The screen shows the guess and its reason, the user can pick
  another, and the test flags capability mismatches.
- [An Anthropic or OpenAI model family has quirks the base harness does not know] → The base is
  conservative (no forced tool call, no vision until the test or the user turns it on); a shipped
  harness can follow once real runs show the need.
- [Two servers that do not fit together, with hot swapping off] → The second fails to load and the
  test or job reports it; PaperDaemon does not guess at VRAM.
- [A job waits a long time on a server that is slowly loading] → The UI shows the load in progress and
  lets the user cancel it; the wait ends if the process dies.

## Migration Plan

The pre-release `models.chat` settings shape and `vram_gb` are replaced. Harnesses were first called
profiles: a slot's `profile` key loads as `harness`, the data folder's `profiles` folder moves to
`harnesses` when first read, and an image slot's retired `coloring_steps` override is dropped (the steps
belong to the coloring book workflow now).

## Open Questions

Can wait:
- More than one saved model per slot, each with its own launch script, for switching between a large
  and a small text model.
- A shortcut to copy the text slot's provider and key into the image slot.
- A shipped harness for a cloud text model once real runs show the base harness falling short.
