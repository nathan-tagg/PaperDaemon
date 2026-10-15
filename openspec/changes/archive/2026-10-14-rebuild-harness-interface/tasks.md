# Tasks

## 1. The interface and the default

- [x] 1.1 `harnesses/text.py`: `TextHarness`, `Turn`, the output outcomes; the default's methods call today's host functions. Check: unit tests for each outcome read from recorded replies Done: `harnesses/text.py`; tests/test_harness_interface.py.
- [x] 1.2 The host runs a job through the harness: intake, output, another turn, ask, skip, jobs, finished page. Check: the baseline prefix and tool schema are byte-identical (`tests/baseline`), and the full suite passes Done: the decision is built by `decision()`, read by `calls`/`read_call`/`outcome`; a FinishedPage commits through the host's own commit; `tools/baseline.py check prefix` same, 394 tests pass.
- [x] 1.3 The assist protocols: the two grounding prompts and the handwriting and picture readings move behind `locate`, `read_ink`, `describe`. Check: unit tests with a stub reply in each format; no prompt text left in the host's callers Done: `locate_many`/`read_located`, `locate_one`/`read_located_one`, `ask`, `describe`; the grounding math checked against the old formula.

## 2. Job kinds

- [x] 2.1 `host/jobs.py`: `JobKind` and the host's protocols, from `steps.KINDS`, `STEP_ALLOWED`, `STEP_TOOLS`. Check: every kind has a protocol; a job of an unknown or off kind is refused with its reason (unit tests) Done: `pipeline/host/jobs.py`; the host's step loop reads the protocols; every step kind checked against `steps.KINDS`.
- [x] 2.2 GAME_TURN through intake. Check: the game tests pass with the bypass gone Done: the harness's `route()` makes a game page a GAME_TURN; the bypass is gone, the game tests pass.

## 3. Harness files

- [x] 3.1 `.py` and skills-only harnesses load from `llm\`; image JSON from `image\`; errors listed. Check: unit tests for a good file, a broken file, a skills-only folder Done: `.py` (one subclass, its server and models checked) and skills folders (`harness.json` + `skills/*.md`) load from `llm\`, image JSON from `image\`; the brief and per-job skills reach the model; tests in test_harnesses.py and test_harness_interface.py.
- [x] 3.2 Declared `server`, `models`, `notes`; names "server - model"; a guide per kind; "+ Add a harness" opens the kind's folder. Check: unit tests (done 2026-10-14)
- [x] 3.3 The old seeded copies and the compatibility code go; the folder is seeded fresh. Check: unit test on a fresh data folder Done: no copies are seeded (the app's harnesses are in the app), the upgrade and refresh code is gone, the old seeded copies were removed from the maintainer's data folder after each was compared with the shipped file.
- [ ] 3.4 The build ships the full standard library. Check: the frozen engine imports a harness that uses `csv` and `statistics` In code: `tools/build_exe.py` collects the standard library (186 modules); the frozen check runs with the next build.

## 4. validate(), capacity, conflicts

- [x] 4.1 validate(): safe area and the stroke limit, with the two fixes. Check: unit tests for each Done: `_validate_draft` at commit (safe area per page frame; PAGE_STROKE_LIMIT 250,000, the rest on a new page after this one) and `_trace_into` redraws with a lower region budget; test_harness_interface.py.
- [x] 4.2 Capacity reads `declare()` (`kinds`, `provides`). Check: unit tests for an unsupported kind and a provided ability Done: `lineup.facts` reads `declare()`; an unsupported kind is off with "this harness does not do ...", a provided ability is on with "the model does it itself"; test_features.py.
- [x] 4.3 Conflict records and CONFLICT jobs, one per page. Check: unit tests with the fake cloud Done: `sync.record_conflict`/`take_conflict` (one per page, newest wins), the daemon hands the oldest over only when no other job is owed, the host renders the set-aside copy with `render.reading()` and asks the harness's `conflict()`; test_sync.py.
- [x] 4.4 The Tests tab names the lineup it tests as a whole. Check: rendered headless Done: the Tests tab's note names the lineup and everything tested with it, in all 14 languages; walked headless (lu_walk).

## 5. Evidence

- [ ] 5.1 With the go-ahead, real jobs on the tablet through the built-in default, compared with the recorded baseline: same pages answered, same turns. Record the result here
