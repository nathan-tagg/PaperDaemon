# Tasks

Tests use their own ports and data folder, and never send requests to model servers the user is
running. Unit tests guard code; only the real runs in group 6 count as evidence.

## 1. Harnesses

- [x] 1.1 Write `paperdaemon/harnesses/base.py` (TextHarness, ImageHarness, the base text and image harnesses) and verify with unit tests that every field has a base value
- [x] 1.2 Write the Qwen 3.6 27B, FLUX.2 Klein 9B and Z-Image Turbo harnesses with their parameters and prompt hooks, and verify with unit tests that Klein's coloring page uses 12 steps and Z-Image's prompt puts the style after the subject
- [x] 1.3 Write the registry and best guess, and verify with a table test: quantized names match their family, Klein base does not match Klein, the hint order is name then server then launch script, and no match falls back to base
- [x] 1.4 Resolve capabilities in layers (override, accepted test result, harness, base) with the source of each value, and verify with a unit test
- [x] 1.5 Clamp the model's own steps to the harness's range and pass the user's explicit steps and seed through; verify with a unit test
- [x] 1.6 Add the protocols to the text harness interface (`intake(job)`, `output(reply, job)`, `tasks` and `validate(result, job)`) with base implementations that work for any model; verify with unit tests that a harness naming none of them runs on the base protocols, that the notebook prompt reaches the model word for word through the base intake, and that each of the base validate()'s refusals fires Superseded by the facelift (5.1): harnesses are data, not code; the host reads their values from the run file, and the feature catalog decides what is offered.
- [x] 1.7 Load harness files from `<data folder>/harnesses/` beside the shipped ones, list each that fails to load or does not satisfy the interface with its error, and verify with fixture files that a good harness appears under its declared name and a broken one stops nothing Done: `tests/test_harnesses.py` (user harnesses override what they name; a broken one is listed with its message and skipped).
- [x] 1.8 Rename profiles to harnesses (code, settings, API, UI, docs) with the settings key and the data folder upgraded on load; verify with unit tests (tests/test_settings.py, tests/test_harnesses.py)
- [x] 1.9 Give image harnesses workflows (the coloring book among them, its wording and steps the harness's alone) and abilities, apply them in the engine by workflow name with LoRAs per request, tell the text model about them in the brief, and verify with unit tests: a workflow's settings applied, no workflow sends the prompt as written, a missing workflow or LoRA falls back and is reported (tests/test_workflows.py)
- [x] 1.10 Make Qwen 3.8 + Klein the shipped default lineup, and verify the 3.8 harness matches a Qwen 3.8 file by name

## 2. Slots and settings

- [x] 2.1 Replace `models.chat` and `vram_gb` with `models.text`, `models.image` and `models.hot_swap`; validate a local slot's loopback endpoint and hot swapping's launch scripts; verify with unit tests for each refusal message
- [x] 2.2 Move the model keys to `key:text` and `key:image` in the credential store and verify the settings file never holds them

## 3. Adapters

- [x] 3.1 Write the OpenAI-compatible and Anthropic chat adapters and verify against recorded request and response shapes that tool calls, forced tool choice and image parts are translated both ways
  - Verified against shapes taken from the APIs' documentation, not recordings from live servers; the live check is 6.1.
- [x] 3.2 Write the Stable Diffusion web UI and OpenAI Images adapters and verify against recorded shapes, including the sd.cpp flow shift block
  - Same: documented shapes; the live check is 6.1.
- [x] 3.3 Verify that an adapter never attaches an image when the slot's effective vision is off (unit test)

## 4. Hot swap

- [x] 4.1 Start a launch script in a hidden console inside a kill-on-close job object (Windows) or its own process group, and verify with a dummy server script on a test port that stop ends the process and its child
- [x] 4.2 Wait for readiness until the server answers or its process exits, and verify both outcomes with dummy scripts
- [x] 4.3 Swap: stop the other slot's server only if PaperDaemon started it, then start this one; verify with two dummy servers, and verify a server PaperDaemon did not start is left running
- [x] 4.4 Bring the text server back after a job that ended on the image server; verify with dummy servers
- [x] 4.5 Store an optional stop script per local slot; to stop a server, run it, then end what remains of the job object or process group; verify with a dummy server whose stop script exits it cleanly, and one whose stop script leaves it running Dropped by the maintainer (a requirement from before the exploration): there are only start scripts. Starting one ends the server PaperDaemon started before for that slot; the scripts do any other stopping.

## 5. API and UI

- [x] 5.1 Add `GET /api/v1/models` (slots, effective harness and why, capabilities with sources, the harnesses on offer, shipped and the user's, and the harness files that failed with their errors), `POST /api/v1/models/{slot}/test`, and start and stop for local slots; verify with API tests Done: `GET /api/v1/models?lineup=` (any lineup's slots, harness and why, capabilities with sources, server state).
- [x] 5.2 Rebuild the models page: two slot panels, harness picker with the guess and its reason, capability list with overrides, launch and stop script editors, hot swapping switch shown only for two local slots with its graphics card notice, the off-machine notice, the test report; verify each state by rendering the page headless Done as the Lineup screen (the maintainer's design): each lineup's Text / Reasoning, Image, Network, Tagging, Memories, Jobs and Tests tabs; walked headless (`paperdaemon-private/tools/walk_lineup.py`).
- [x] 5.3 Document slots, harnesses and hot swapping in the README, and verify the documented steps match the screen

## 6. Real-run evidence

- [ ] 6.1 With the maintainer's go-ahead and the maintainer's card free: set both slots local with launch scripts for Qwen 3.6 27B and FLUX.2 Klein 9B, turn hot swapping on, run the test on each slot, and record the guessed harnesses, the check results and the swap times here
- [ ] 6.2 Point the text slot at a cloud model on the base harness, run the test, and record which capabilities the checks found
