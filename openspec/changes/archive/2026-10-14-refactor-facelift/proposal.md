# Proposal

## Why

The code works, but it is hard to read, slow to change and in places at odds with how the maintainer
wants PaperDaemon to behave:

- **Too many flat files, and two giants.** The pipeline is 69 flat modules (61 of them `rm_*.py`) that
  import each other by bare name through a `sys.path` entry. Beside them sit two files nobody can hold in
  their head: `rm_host.py` (7,653 lines, one global `JOB` dict with 64 keys used 435 times) and
  `rm_chart.py` (5,057 lines).
- **Things done twice.** Two reMarkable sync clients (24 functions of the same name), two handwriting
  readers, two notepad implementations, two path modules, two model clients, and settings rules
  repeated in the engine, the slots, the harness rules and the UI.
- **The host decides what the model should.** About thirty places in the host and its step parser
  change a job by matching words (a plan step rewritten because it says "chart", a paragraph kept
  because it ends in a question mark, a Reddit search rebuilt from its wording). Each was added after
  one incident and overfits the phrasing it was tuned on. The maintainer wants those decisions to be the
  model's, with real turns to look before it rules, and the host to enforce only validity.
- **Harness differences are code.** A harness can still carry Python hooks, and the host offers tasks by
  a few hard-wired capability checks. The maintainer wants one interpreter driven by the data a harness
  provides, never an executor per model, and a feature list in which features can require other
  features.
- **Dead and report-only code** (measured in design.md) and model calls bounded by a clock, which the
  standing rules forbid.

The repository is about to be published, so the cleanup happens before the first commit.

## What Changes

- **Packages, fewer files.** The pipeline's flat modules move into packages (`host`, `host/features`,
  `page`, `draw`, `charts`, `games`, `decompose`, plus the daemon), small single-use modules fold into
  their users, the eight face modules become three, `rm_host.py` splits into a host core and feature
  modules, and `rm_chart.py` splits by chart family. The decomposer's Python reference moves without a
  change to its code.
- **Objects where there is state.** A `Host` class (job loop, model turns, step routing), `Page`, `Job`
  and `Step` models in place of the `JOB` dict, and a `Feature` base class with one subclass per
  feature. On the engine side, `Harness`, `Slot`, `Lineup` and `FeatureSet`. Plain functions stay
  plain where there is no state: raster math, geometry, layout, chart builders, the C wrappers.
- **A data-driven feature list.** Each feature declares what it requires: text capabilities, image
  abilities and workflows, a search provider, installed content, a filled setting, and other features.
  A requirement is hard (the feature is off without it) or optional (the feature degrades). Cycles are
  refused at startup. The engine resolves the features when a lineup is activated and writes them,
  with each "off because ..." chain, into the host's run file. The host builds the model's
  instructions and tools only from the enabled features and refuses steps of disabled ones. The Models
  screen shows the resolved features per lineup.
- **Harnesses are data.** Shipped harnesses become JSON files in the same format as the user's own.
  The last code hook (`tune`) becomes request data keyed by a capability's value.
- **The model decides; the host checks validity.** The decision turn gets structured fields in place
  of the host's word matching: a ruling for every item new since the last job, the items each step
  answers, the picture a step replaces, explicit step kinds, structured sources, quoted citations.
  Before ruling, the model may inspect: look closer at a region or an item, read the notepad, see what
  changed since the last job and the page's history, bounded by tokens and repetition, never a clock.
  The host enforces only validity: ids exist, rulings are complete and consistent, moves are legal,
  capabilities and features allow the step, things stay in the safe area, citations are found.
- **Keyword assists, only by a harness's choice.** A harness for a weaker model may carry keyword
  assists as data, each named for one decision, with its keyword lists and either a hint (preferred) or
  an override. The default harness carries none. Every removed check's incident becomes a test case.
- **One settings schema** read by the API, the UI and validation; the pipeline's hidden environment
  settings are classified and either join the schema, stay as wiring, or go.
- **One model client** for the host's turns, through the engine's adapters, stopped by tokens and
  repetition only.
- **Build and dependencies.** `tools/build_app.py` builds the C decomposer first. Once the single C
  decomposer call is finished, OpenCV, numba (with llvmlite), SciPy, scikit-image and Shapely move to a
  test-only dependency group, after a test proves the app's run-time imports load none of them.

## Capabilities

### New Capabilities
- `jobs/features`: the feature list, hard and optional requirements, resolution at lineup activation,
  the run file, refusing disabled steps, and the Models screen's view of it.
- `jobs/decisions`: the model's structured decision, its inspection turns and their bounds, the
  host's validity rules, and keyword assists applied from harness data.

### Modified Capabilities
- `jobs/host`: the job runs by the harness's data and the resolved features; validity replaces
  validate(); tasks follow the resolved features; a harness no longer hands back a finished page.
- `jobs/cleanup`: what comes off is decided by the model's rulings; the host's carried-out test goes.
- `jobs/tags`: a tag's direction is a quoted citation the host verifies.
- `models/harnesses`: a harness is data, shipped and user harnesses share one format, a harness may
  narrow what the host offers but never loosen validity, keyword assists, and the user's step count as a
  citation.
- `extensions/tools`: a tool is a feature, and its needs include other features.
- `engine/settings`: one schema describes every setting.
- `packaging/desktop`: the build compiles the decomposer first, and the app ships only run-time
  dependencies.

## Non-goals

- Any change to the decomposer's algorithm, constants or output, to its C code, or to `rm_model.py`
  while another job completes the single C decomposer call.
- New job types, new models or new harness families.
- A redesign of the UI beyond the Models screen's feature panel and forms that read the settings schema.
- Tuning the brief. Its wording changes only where a removed check or a new field needs it.
- Prices, cost displays or usage metering of any kind.

## Impact

- Code: every module under `paperdaemon/pipeline/` moves; `paperdaemon/remarkable/`, `paths.py`,
  `settings.py`, `harnesses/`, `models/`, `loop.py`, `server.py`, `studio.py`, `records.py` and the UI's
  models and settings screens change. The full map is in design.md.
- Processes: the daemon and the host start as modules (`python -m ...`), and the packaged app's hidden
  `--run-pipeline` entry takes a module name.
- The host's run file replaces `RM_HARNESS` and the `RM_LLM_*` environment; settings reach the host only
  through it.
- API: new routes for the settings schema and a lineup's resolved features.
- Dependencies: `pyproject.toml` gains a test-only group for the decomposer's Python reference.
- Specs: deltas against capabilities defined in the still-open changes `add-job-host`,
  `add-model-slots-and-harnesses`, `add-tool-extensions`, `add-engine-foundation` and
  `add-desktop-packaging`. This change is archived after them.
