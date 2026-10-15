# Design

## Context

The host (`pipeline/host/__init__.py`, about 7,400 lines) holds the brief, the decision tool, the step turns, the
grounding prompts and the reading of every reply. Harnesses are JSON data (facelift 5.1): capabilities, request
fields, workflows. The September spec (add-model-slots-and-harnesses) already said a text harness is a set of
protocols; this change builds that, with the user's rulings of 2026-10-14 (recorded in the proposal page they
reviewed).

## Decisions

### The interface lives in the package; the default carries today's code
`paperdaemon/harnesses/text.py` defines `TextHarness`, whose methods are the interface. The built-in default is
`TextHarness` itself: its methods call the host's existing functions (the brief, `job_context`, the page image,
the plan tool, `_turn`'s reading of a tool call, the two grounding prompts), so nothing a model sees changes. The
host process imports it; the engine imports only `declare()` data from it. Moving the text of the prompts into
skill files comes after the byte-identical check holds, one skill at a time.

### Turns go through the host; harnesses never call the model
A harness builds a `Turn` (messages, tools, tool choice, temperature, max tokens, an optional schema) and reads a
reply. The host sends turns through the engine, so the token and repetition guards, the adapters and the request
fields stay in one place, and a harness cannot reach the network on its own behalf.

### Job kinds and their protocols are the host's
`pipeline/host/jobs.py` holds `JobKind` and one `JobProtocol` per kind: `model_part`, the turn builder, the reader,
`back_to_model`. They are today's `steps.KINDS`, `STEP_ALLOWED` and `STEP_TOOLS`, gathered. A harness may replace
a protocol through a mapping; the default's mapping is empty. GAME_START and GAME_TURN split today's `game` step;
NOTE and REMEMBER are today's notepad tool and `remember` field; PICTURE_EDIT is the image step with a source.

### User harnesses
- `llm\<name>.py`: imported with `importlib` from its path; it must define exactly one subclass of `TextHarness`
  with `id`, `name`, `server`, `models`. Errors (import, no class, two classes, a missing field) are listed.
- `llm\<name>\harness.json` + `skills\*.md`: a skills-only harness: the JSON names it and declares its fields;
  each skill file replaces the default's skill of that name.
- The model's per-model data (vision, forced tool, output size, request fields, patterns) stays JSON, now the
  `model` block of a harness, so guessing by model name still works.
- The frozen app ships the full standard library (`--collect-submodules` over the stdlib list), so a harness can
  import what Python ships.

### validate()
The default's checks: staged ink and pictures inside the safe area; the page's stroke count after commit at most
250,000 (a placeholder until a real page shows the tablet's own limit). Over the limit: a WRITE's remaining lines
move to a new page after this one; a decomposed picture is redone with the region budget lowered until it fits.

### Conflicts
`sync.pull` already sets ours aside (`conflicts/<time>/`). It now also writes a conflict record (doc, page id,
the set-aside path, the job's key) that the daemon turns into a CONFLICT job, replacing any queued one for the
same page. The host's CONFLICT protocol hands both page images and the job's plan to the harness's `conflict`.

### Capacity
`declare()` adds two facts per lineup: `kinds` (the job kinds the harness supports) and `provides` (abilities met
by the model itself: `pictures`, `search`). A kind not supported is off: "this harness does not do <kind>".

## Rejected alternatives

- **Harnesses as data only** (facelift 5.1): cannot express another tool shape or a model that does the whole
  job; the user asked for an interface.
- **Harnesses calling the model themselves**: would bypass the token and repetition guards and the adapters.
- **Job protocols in every harness**: the user ruled the host holds them; harnesses rarely change them.
- **Keeping old harness files working**: no lineup uses a harness yet; the old copies are cleared, not migrated.

## Open Questions

- The tablet's real stroke limit per page (250,000 is a placeholder).
