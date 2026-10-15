# Proposal

## Why

The pipeline was built around one pair of models on one card: Qwen 3.6 27B for words and FLUX.2 Klein for
pictures, swapped in and out of 24 GB of VRAM. PaperDaemon has to run with whatever the user has: a local
server, a cloud API, or one of each. Models differ in ways that change what the host may ask of them
(whether they can see a page, whether a tool call can be forced, how many steps a picture needs), so
those differences need a home that is not a fork of the host.

## What Changes

- Two model slots: **text and reasoning**, and **image**. Each has an endpoint, an optional key, a
  model name, an API family, a harness, and optional capability overrides. They may use the same
  endpoint and provider.
- API families: OpenAI-compatible chat and Anthropic Messages for text; the Stable Diffusion web UI API
  and the OpenAI Images API for pictures.
- **Harnesses**, one per model family and parameterization: a base harness for each slot that runs any
  model on best guesses, plus Qwen 3.6 27B, FLUX.2 Klein 9B and Z-Image Turbo. PaperDaemon guesses the
  harness from what it can see; the user can pick another.
- A **Test this model** action per slot that shows what actually works: reachable, the model the
  server reports, tool calls and vision for text, a small render for pictures.
- **Hot swapping** for two local servers that cannot share the card: each local slot keeps an editable
  launch script, and PaperDaemon starts and stops the servers it launched as jobs need them. This is how
  PaperDaemon matches the pipeline's studio.
- A plain notice whenever a slot's endpoint is off this machine.

## Capabilities

### New Capabilities
- `models/slots`: the two slots, their settings, API families, the off-machine notice and the model test.
- `models/harnesses`: base and shipped harnesses, best-guess selection, the user's choice, capability
  overrides, and the parameter ranges a harness sets.
- `models/hot-swap`: launch scripts, starting and stopping local servers PaperDaemon launched, and which
  server stays up between jobs.

### Modified Capabilities
None.

## Non-goals

- The job host itself and the brief it sends (add-job-host). This change gives the host the slots and
  their capabilities.
- Harnesses beyond base, Qwen 3.6 27B, FLUX.2 Klein 9B and Z-Image Turbo.
- ComfyUI and other image API families; more than one saved model per slot.
- Loading harnesses from the user's data folder.
- Any display of prices or usage.

## Impact

- New package `paperdaemon/harnesses/` (base, registry, three shipped harnesses) and `paperdaemon/models/`
  (slots, adapters, hot swap).
- Settings gain `models.text`, `models.image` and `models.hot_swap`; the earlier `models.chat` shape
  and `vram_gb` go away before any release.
- New API routes under `/api/v1/models`; the models page of the UI is rebuilt.
- The hot swap runs user-written launch scripts on this machine.
