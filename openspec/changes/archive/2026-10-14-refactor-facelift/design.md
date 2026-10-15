# Design

## Context

See proposal.md for why. Every number below was measured on the working tree:

- line counts with `wc -l`;
- importers from each file's import statements, by an AST walk that also follows imports inside
  functions;
- dead code as top-level functions never referenced by name anywhere in the repository's Python,
  JavaScript, HTML or JSON (decorated functions are left out, so API routes and registered face parts are
  not counted);
- run-time dependencies by importing modules in a fresh interpreter and reading `sys.modules`.

### The current inventory

110 Python modules, 56,266 lines, under `paperdaemon/`. 193 unit tests are collected
(`pytest --collect-only`). Four test files (`test_chess_and_safe_area`, `test_erase_ids`,
`test_fixed_tags`, `test_workflows`) drive pipeline modules in a child process, importing them inside a
code string; the tables count them only where the text says so.

Engine, `paperdaemon/` (35 modules, 5956 lines):

| Module | Lines | Imported by |
|---|---:|---|
| `__init__` | 2 | the package itself |
| `__main__` | 106 | the entry point (`uv run paperdaemon`); 1 test file |
| `benchmark/__init__` | 321 | `server`; 2 test files |
| `benchmark/fixtures` | 147 | run as a module to build the fixtures; 1 test file |
| `card` | 444 | `loop`, `models/checks`, `server`; 4 test files |
| `desktop` | 10 | `__main__` |
| `harnesses/__init__` | 129 | `models/slots`, `server`; 3 test files |
| `harnesses/base` | 198 | `card`, `harnesses/__init__`, `harnesses/flux2_klein_9b`, `harnesses/qwen3_6_27b`, `harnesses/qwen3_8_27b`, `harnesses/rules`, `harnesses/z_image_turbo`; 2 test files |
| `harnesses/flux2_klein_9b` | 24 | `harnesses/__init__`; 1 test file |
| `harnesses/qwen3_6_27b` | 22 | `harnesses/__init__`; 2 test files |
| `harnesses/qwen3_8_27b` | 24 | `harnesses/__init__`; 1 test file |
| `harnesses/rules` | 83 | `harnesses/user`, `models/slots`; 1 test file |
| `harnesses/user` | 148 | `harnesses/__init__`; 1 test file |
| `harnesses/z_image_turbo` | 22 | `harnesses/__init__`; 1 test file |
| `loop` | 349 | `benchmark/__init__`, `server`; 2 test files |
| `models/__init__` | 2 | `card`, `loop`, `server`, `settings`; 4 test files |
| `models/adapters` | 372 | `card`, `models/checks`, `models/hotswap`, `server`; 1 test file |
| `models/checks` | 136 | `server`; 2 test files |
| `models/hotswap` | 396 | `card`, `server`; 1 test file |
| `models/slots` | 174 | `card`, `loop`, `models/adapters`, `models/checks`, `models/hotswap`, `server`, `settings`; 2 test files |
| `paths` | 39 | `__main__`, `benchmark/__init__`, `card`, `harnesses/__init__`, `loop`, `models/hotswap`, `pipeline_env`, `records`, `remarkable/sync`, `scripts`, `settings`, `studio`; 4 test files; `tools/import_state` |
| `pipeline_env` | 35 | `studio` |
| `reader/__init__` | 88 | `reader/winocr`; 1 test file |
| `reader/render` | 50 | `reader/__init__`; 1 test file |
| `reader/winocr` | 54 | `reader/__init__` |
| `records` | 115 | `server`; 1 test file |
| `remarkable/__init__` | 1 | `loop`, `server`; 3 test files |
| `remarkable/auth` | 80 | `loop`, `remarkable/sync`, `server`; 2 test files |
| `remarkable/desktop_token` | 94 | `server`; 1 test file |
| `remarkable/sync` | 812 | `server`; 2 test files |
| `scripts` | 154 | `__main__`, `card`, `models/hotswap`, `models/slots`, `server`; 1 test file |
| `server` | 742 | `__main__`; 3 test files; `tools/ui_shot` |
| `settings` | 277 | `__main__`, `benchmark/__init__`, `card`, `loop`, `models/hotswap`, `models/slots`, `pipeline_env`, `server`, `studio`; 7 test files; `tools/ui_shot` |
| `studio` | 269 | `server`; 1 test file |
| `vault` | 37 | `models/adapters`, `remarkable/auth`, `server`; 2 test files |

Pipeline, `paperdaemon/pipeline/` and `pipeline/fastdecomp/` (75 modules, 50310 lines):

| Module | Lines | Imported by |
|---|---:|---|
| `coloring_pages` | 868 | `rm_elements` |
| `fastdecomp/build` | 62 | `fastdecomp/rmfast` |
| `fastdecomp/rmbudget` | 77 | `rm_model` |
| `fastdecomp/rmfast` | 1000 | `rm_model` |
| `fastdecomp/rmpaint_fast` | 1540 | `rm_model` |
| `fastdecomp/rmreuse` | 116 | `rm_model` |
| `fastdecomp/rmstore` | 353 | `rm_model` |
| `rm_adventure` | 1871 | `rm_games`, `rm_host` |
| `rm_arrows` | 168 | `rm_host` |
| `rm_art` | 738 | `benchmark/fixtures`, `coloring_pages`, `rm_adventure`, `rm_chart_strokes`, `rm_daemon`, `rm_host`, `rm_images`, `rm_model`, `rm_paint`, `rm_sig`, `rm_typed`, `studio` |
| `rm_cast` | 180 | `rm_characters`, `rm_chess`, `rm_faces`, `rm_games`, `rm_messages`, `rm_residents`, `rm_table`, `rm_tabletop_schema` |
| `rm_characters` | 1381 | `rm_chess`, `rm_games`, `rm_messages`, `rm_residents`, `rm_table`, `rm_tabletop` |
| `rm_chart` | 5057 | `rm_characters`, `rm_chart_strokes`, `rm_games`, `rm_host`, `rm_tabletop` |
| `rm_chart_strokes` | 485 | `rm_elements`, `rm_host` |
| `rm_chess` | 1417 | `rm_adventure`, `rm_games`, `rm_host`, `rm_messages`, `rm_residents` |
| `rm_cloud` | 1131 | `rm_adventure`, `rm_daemon`, `rm_folders`, `rm_host`, `rm_images`, `rm_pdfdoc`, `rm_render`, `rm_scan`, `studio` |
| `rm_content` | 168 | `rm_adventure`, `rm_cast`, `rm_characters`, `rm_chart`, `rm_chess`, `rm_faces_portraits`, `rm_font`, `rm_games`, `rm_history`, `rm_host`, `rm_messages`, `rm_pdfdoc`, `rm_sig`, `rm_weather`, `typed_layout` |
| `rm_daemon` | 1069 | run as a child process by `loop.py` |
| `rm_elements` | 623 | `rm_host`, `rm_text` |
| `rm_erase` | 272 | `rm_games`, `rm_host`, `rm_messages`, `rm_typed` |
| `rm_faces` | 841 | `rm_characters`, `rm_chess`, `rm_faces_beasts`, `rm_faces_fine`, `rm_faces_folk`, `rm_faces_habits`, `rm_faces_machines`, `rm_faces_portraits`, `rm_faces_wear` |
| `rm_faces_beasts` | 483 | loaded by the plugin glob in `rm_faces.py:832-841` |
| `rm_faces_fine` | 197 | loaded by the plugin glob in `rm_faces.py:832-841` |
| `rm_faces_folk` | 1109 | `rm_faces_fine` |
| `rm_faces_habits` | 36 | loaded by the plugin glob in `rm_faces.py:832-841` |
| `rm_faces_machines` | 808 | loaded by the plugin glob in `rm_faces.py:832-841` |
| `rm_faces_portraits` | 63 | `rm_faces` |
| `rm_faces_wear` | 458 | loaded by the plugin glob in `rm_faces.py:832-841` |
| `rm_flow` | 200 | `fastdecomp/rmpaint_fast`, `rm_paint` |
| `rm_folders` | 99 | `rm_adventure`, `studio` |
| `rm_font` | 155 | `rm_chart` |
| `rm_games` | 731 | `rm_adventure`, `rm_host` |
| `rm_glyphs` | 324 | `rm_chart`, `rm_tabletop` |
| `rm_history` | 79 | `rm_host` |
| `rm_holidays` | 198 | `rm_chart` |
| `rm_host` | 7653 | run as a child process by `loop.py`; 2 test files and `tools/check_schema_order.py` import it inside a child process |
| `rm_icons` | 812 | `rm_chart`, `rm_elements` |
| `rm_images` | 866 | `rm_adventure`, `rm_art`, `rm_chess`, `rm_games`, `rm_host`, `rm_messages`, `rm_render`, `rm_scan` |
| `rm_lean` | 688 | `rm_model` |
| `rm_lineart` | 390 | `rm_host` |
| `rm_marks` | 252 | `rm_arrows`, `rm_host` |
| `rm_messages` | 499 | `rm_games`, `rm_host` |
| `rm_model` | 348 | `rm_adventure`, `rm_host`, `studio` |
| `rm_ocr` | 133 | `rm_host` |
| `rm_page` | 666 | `rm_adventure`, `rm_chess`, `rm_daemon`, `rm_games`, `rm_host`, `rm_images`, `rm_marks`, `rm_pdfdoc`, `rm_plan`, `rm_render`, `studio` |
| `rm_pages` | 214 | `rm_adventure`, `rm_host`, `rm_messages`, `rm_pdfdoc` |
| `rm_paint` | 3226 | `rm_chart_strokes`, `rm_host`, `rm_model`, `rm_regions`, `studio` |
| `rm_pdfdoc` | 398 | `rm_adventure`, `rm_characters`, `rm_games`, `rm_host` |
| `rm_pdftext` | 270 | `rm_host` |
| `rm_plan` | 466 | `rm_host` |
| `rm_raster` | 254 | `rm_lean`, `rm_model` |
| `rm_reddit` | 361 | `rm_host` |
| `rm_regions` | 276 | `rm_model` |
| `rm_render` | 653 | `rm_adventure`, `rm_arrows`, `rm_art`, `rm_cloud`, `rm_daemon`, `rm_erase`, `rm_games`, `rm_host`, `rm_images`, `rm_lean`, `rm_marks`, `rm_messages`, `rm_page`, `rm_pages`, `rm_paint`, `rm_pdfdoc`, `rm_pdftext`, `rm_typed`, `studio` |
| `rm_residents` | 281 | `rm_chess`, `rm_games`, `rm_messages` |
| `rm_scan` | 883 | `rm_adventure`, `rm_cloud`, `rm_daemon`, `rm_host`, `rm_messages`, `rm_pages`, `rm_render` |
| `rm_serif` | 241 | `rm_text` |
| `rm_sig` | 278 | `rm_daemon`, `rm_elements` |
| `rm_social` | 303 | `rm_host` |
| `rm_steps` | 485 | `rm_host`; 1 test file |
| `rm_table` | 341 | `rm_chess`, `rm_games`, `rm_messages` |
| `rm_tabletop` | 592 | `rm_chart` |
| `rm_tabletop_schema` | 100 | `rm_chart`, `rm_tabletop` |
| `rm_text` | 569 | `benchmark/fixtures`, `coloring_pages`, `rm_chart`, `rm_chart_strokes`, `rm_font`, `rm_glyphs`, `rm_host`, `rm_serif`, `rm_sig`, `rm_typed` |
| `rm_trace` | 191 | `rm_lineart`, `rm_paint` |
| `rm_typed` | 632 | `benchmark/fixtures`, `rm_daemon`, `rm_host`, `rm_images`, `rm_marks`, `rm_page`, `rm_render` |
| `rm_weather` | 231 | `rm_chart` |
| `rm_wxicons` | 176 | `coloring_pages` |
| `rmb_geometry` | 291 | `rm_model`, `rm_paint` |
| `rmb_lineart` | 220 | `rm_model`, `rm_paint` |
| `rmb_npops` | 577 | `fastdecomp/rmfast`, `rm_model`, `rm_paint`, `rmb_lineart` |
| `rmb_params` | 798 | `rm_model`, `rm_paint`, `rm_regions` |
| `rmb_resolution` | 80 | `fastdecomp/rmpaint_fast`, `rm_paint` |
| `typed_layout` | 165 | `rm_typed` |
| `typed_records` | 94 | `rm_typed`, `typed_layout` |

### Measured after the facelift (2026-10-14)

131 Python modules, 57,582 lines, under `paperdaemon/`; 479 unit tests. No flat module is left in
`paperdaemon/pipeline/`: every part is a package. The host, one 7,474-line module before, is a package of 24 modules
(`host/` 5,320 lines, `host/features/` 2,882), with the job's state a typed object (`host/job.py`).

| Package | Modules | Lines |
|---|---|---|
| the engine (`paperdaemon/*.py`) | 22 | 5,419 |
| `benchmark` | 3 | 838 |
| `harnesses` | 3 | 897 |
| `models` | 6 | 1,263 |
| `reader` | 3 | 240 |
| `remarkable` | 8 | 1,970 |
| `pipeline/charts` | 9 | 7,523 |
| `pipeline/daemon` | 2 | 828 |
| `pipeline/decompose` | 21 | 11,025 |
| `pipeline/draw` | 7 | 3,176 |
| `pipeline/features` | 1 | 195 |
| `pipeline/games` | 14 | 11,784 |
| `pipeline/host` | 13 | 5,320 |
| `pipeline/host/features` | 11 | 2,882 |
| `pipeline/page` | 7 | 4,215 |

### What the measurements show

**The host.**

- `rm_host.py` is 7,653 lines. It offers the model 19 tools, holds 28 `t_*` tool functions (8 never
  called), and keeps a job's state in one module-level `JOB` dict: 64 keys, read or written 435 times.
- 880 comment lines and 710 docstring lines (21% of the file), many of them incident narratives.
- Its first 75 lines are a function placed above the module docstring, so the file has no docstring.
- Its static prompt prefix is 14,931 characters of tool schema and 6,741 of brief; the erase enum holds
  181 ids.
- It imports `rm_paint` and `rm_lineart` and never uses them. Importing the host loads OpenCV, numba,
  llvmlite and SciPy.

**Things done twice.**

| What | Where | Measured |
|---|---|---|
| reMarkable sync client | `remarkable/sync.py` (812), `pipeline/rm_cloud.py` (1,131) | 24 functions and classes of the same name: `CloudBusy`, `Notifier`, `_call`, `_keep_our_pages`, `_save_state`, `_state`, `_write_atomic`, `changed_files`, `crc32c`, `get_blob`, `get_root`, `get_snapshot`, `goog_hash`, `index_hash`, `notify_host`, `pull`, `push_doc`, `push_new_doc`, `put_blob`, `put_root`, `rollback`, `save_undo`, `snapshot`, `touch`. With docstrings set aside, 11 are identical and 13 have drifted apart, most in `push_doc`, `push_new_doc`, `snapshot`, `rollback` and `_state` |
| device and user tokens | `remarkable/auth.py`, `rm_cloud.py` | `device_token` and `user_token` in both |
| handwriting reader | `reader/` (WinRT, in process), `rm_ocr.py` (PowerShell) | the reader is the specified one; the host uses `rm_ocr` |
| notepad | `records.py`, `rm_host.py:1216-1500` | file path, entry format and wipe in both |
| data and content paths | `paths.py`, `rm_content.py` | `rm_content.home()` also reads `settings.json` itself, as a fallback |
| fixed tag names | `settings.py`, `rm_scan.py` | the same two names, held twice |
| model client | `rm_host.py:6086` `chat()` (raw OpenAI-compatible HTTP), `models/adapters.py` | the engine's proxy forwards the host's request untranslated, so a text slot with `api: anthropic` cannot run jobs |
| settings rules | `settings.py`, `models/slots.py`, `harnesses/rules.py`, `ui/network.js:93`, `ui/tablet.js:132` | the port range and the inbox rule are restated in the UI |

**Dead and report-only code.**

| Where | Lines | What |
|---|---:|---|
| `rm_host.py` | 220 | `t_measure_text` :514, `t_clear` :1196, `t_note` :1489, `t_type_text` :4512 (marked unregistered), `t_erase_marks` :5574, `t_erase_area` :5603, `t_done` :5652, `scratch_message` :6312 |
| `rm_daemon.py` | about 170 | a brief for an interactive agent session (`PROMPT` :204, `BATCH_NOTE` :285, `build_prompt` :333), written to a file the host deletes unread; the body of `close_desktop_app` after its `return []` (:755); three switches that reach only a log line (`RM_MODEL`, `RM_EFFORT`, `RM_PERMISSION_MODE`) and an unused kill switch (:101) |
| other pipeline modules | 421 | `rm_page` (`check_safe_area`, `render_subset`, `what_is_at`: 119), `rm_characters` (`write_gallery`, `build_faces`, `overall`, `cover_png`: 87), `rm_chart` (5 helpers: 60), `rm_adventure` (`convert_to_book`, `write_box_page`: 36), `rm_games.new_notebook` (29), `rm_images.remove_all` (27), and 12 smaller ones in 10 modules (63) |
| engine | 14 | `card.wait_idle`, `benchmark._status_of` |
| unreachable at run time (removal needs the maintainer's word) | 1,334 | `coloring_pages.py`: 768 of its 868 lines (four hand-drawn pages and their decorations; `rm_elements` uses 13 helpers, 100 lines); `rm_wxicons.py` (176), used only by those pages; `rm_lineart.py` (390), imported only by the host's unused import |
| developer commands | | 30 pipeline modules carry an `if __name__ == "__main__"` block |

The decomposer's own unused helpers (`rm_model`, `rm_paint`, `rmb_geometry`, `rmb_npops`: 79 lines) are
left alone with the rest of the reference.

**Clock limits on model calls**, against the standing rule that runaway output is stopped by tokens and
repetition:

- `rm_host.py:211` `ensure_server` gives up after 300 s;
- `rm_host.py:6238` `TURN_TIMEOUT` (600 s) is the socket timeout of the streamed turn (:6118) and of three
  unstreamed model calls, where it cuts off a slow model's whole reply: grounding (:3222), `find`
  (:4625) and the games' `_ask` (:7281);
- picture calls wait at most 900 s (`_studio_open` :2055, `_slot` :2070).

Timeouts on web requests (search, feeds, downloads) are not model limits and stay.

**Hidden settings.** The pipeline reads at least 53 `RM_*` environment variables (literal reads). They
are of four kinds:

- wiring the engine sets for its children: `RM_STATE`, `RM_MIRROR`, `RM_CACHE`, `RM_TRIGGER`, `RM_LLM`,
  `RM_STUDIO`, and the like;
- settings with no place in the settings file: `RM_CALENDAR_MODE`, `RM_CHART_PATH`, `RM_OUTPUT_FOLDER`,
  `RM_HOME_PLACE`, `RM_HOME_LAT`, `RM_HOME_LON`, `RM_HOLIDAYS`, and `RM_MAP_KEY`, which went with
  the street maps;
- developer switches: `RM_FAST`, `RM_FAST_STAGES`, `RM_HOST_DRAW_LOOKS`, `RM_DECIDE_TEMP`, and others;
- leftovers: the four daemon switches above.

One of the wiring values is a hidden limit: `loop.py:122` sets `RM_HOST_TURNS=24`, which the host's own
comment (`rm_host.py:138-148`) calls a switch for debugging a runaway. Every job is cut off after 24 model
turns.

**A spec and the code disagree.** The open add-model-slots-and-harnesses spec says the base text
harness assumes no vision and asks for, rather than forces, a tool call. `harnesses/base.py` defaults to
vision on and a forced tool call. This change keeps the code's values and leaves the question open.

**Heavy dependencies at run time**, by importing each module in a fresh interpreter:

- the engine (`paperdaemon.server`), the daemon, `rm_chart`, `rm_elements`, `rm_games` and
  `paperdaemon.studio` load none of OpenCV, numba, llvmlite, SciPy, scikit-image or Shapely;
- `rm_model` (the decomposer) loads the first four, and so does `rm_chart_strokes`, through `rm_paint`
  (it uses `rm_paint._lab` and `rm_paint.render`);
- `studio.py` uses `rm_paint.render` for its preview; `rm_elements` reaches `rm_chart_strokes.parse_path`
  inside a function;
- scikit-image and Shapely are imported only by `rmb_geometry`, the Python ring planner;
- SciPy is imported by `fastdecomp/rmpaint_fast.py` (:431, :920, :1117) and by `rmb_npops`, which
  `fastdecomp/rmfast.py` imports, so today's fast path still needs it.

## Goals / Non-Goals

**Goals:**
- No flat module left in `paperdaemon/pipeline/`; fewer, cohesive files in packages.
- One definition of each thing: sync client, tokens, reader, notepad, paths, settings rules, model client.
- One interpreter, driven by the harness's data and the resolved features; never a branch on a model.
- The model makes the decisions after real turns to look; the host checks validity.
- Every migration step small, independently testable, and green on the unit tests, the benchmark and
  the decomposer identity.
- No clock on a model call.

**Non-Goals:**
- Changing what the decomposer produces, its C code, or `rm_model.py` before the single-call work lands.
- Changing behavior in the structure-only steps. They are proven equal before any decision moves.
- Shortening or retuning the brief beyond what a removed check or a new field needs.

## Decisions

### 1. Packages, and the target map

The flat modules move into packages that import each other by package path. The `sys.path` entry
(`pipeline_env.py`) goes. Single-use small modules fold into their one user. Each move rewrites every
importer in the same step; no re-export shims are left behind.

**Engine, `paperdaemon/`**

- `__init__.py`: the package.
- `__main__.py`: starts the engine and the window; `--run-pipeline <module>` in the packaged app. Takes
  in `desktop.py` (10 lines, one user).
- `server.py`: the local API and the host's surfaces. Adds the routes for the settings schema and a
  lineup's features.
- `settings.py`: the settings `SCHEMA`, and loading, merging, validating and saving from it.
- `paths.py`: every folder (data, mirror, state, content, output folder, caches). Takes in `rm_content`.
- `vault.py`: the credential store.
- `ledger.py`: the job ledger, written by the daemon and the host and read by the screens. Takes in
  `rm_scan` and the ledger half of `records.py`.
- `scripts.py`, `studio.py`, `loop.py`, `card.py`: as today. `loop.py` activates a lineup through
  `Lineup.activate()`.
- `benchmark/__init__.py`, `benchmark/fixtures.py`: as today.
- `harnesses/__init__.py`: `Harness` and the registry: one loader for shipped and user files,
  inheritance, the best guess. Takes in `base.py` and `user.py`.
- `harnesses/schema.py`: every harness field with its rule and default, and the assist format. Takes in
  `rules.py`.
- `harnesses/shipped/*.json`: six data files (default-text, default-image, qwen3.6-27b, qwen3.8-27b,
  flux.2-klein-9b, z-image-turbo) in place of the four model modules and the two default classes.
- `harnesses/examples/*.json`: the LoRA workflow example and a keyword-assist example, both inactive.
- `models/adapters.py`, `models/checks.py`, `models/hotswap.py`: as today; the adapters also serve the
  host's turns.
- `models/lineup.py`: `Slot`, `Lineup` and `FeatureSet`: layered capabilities, activation, the run file.
  Takes in `slots.py` and `loop.harness_values()` / `write_harness()`.
- `reader/__init__.py`: the reader interface and the ink renderer (takes in `reader/render.py`);
  `reader/winocr.py`: the Windows engine. `rm_ocr.py` goes.
- `remarkable/auth.py` (one copy of the tokens), `remarkable/desktop_token.py`, `remarkable/sync.py`
  (the one sync client: today's file merged with `rm_cloud.py`), `remarkable/library.py` (folders and
  pages at the file level: `rm_folders` and `rm_pages`).

**Pipeline, `paperdaemon/pipeline/`**

- `__init__.py`: the package.
- `daemon.py`: watches the mirror and queues jobs; `python -m paperdaemon.pipeline.daemon`. `rm_daemon`
  without the legacy dispatch.
- `host/`
  - `__init__.py`: `Host`: the queue loop, a job from reading to record, model turns, step routing.
  - `__main__.py`: `python -m paperdaemon.pipeline.host`.
  - `job.py`: the `Item`, `Page`, `Ruling`, `Step`, `Decision` and `Job` models and the step order
    (`rm_steps` without its text parsers).
  - `commit.py`: the `Draft` (strokes, pictures, documents, staged erasures, tags), the snapshot, the
    commit, and the check after it.
  - `intake.py`: the page as the model is shown it: the listing with ids, what is new since the last job,
    the page image or its text form, the notebook's prompt.
  - `decision.py`: the decision turn: the schema built from the enabled features, inspection turns and
    their budget, the validity checks, assists.
  - `layout.py`: the layout solver and placement (`rm_plan` and the host's placement helpers).
  - `notebook.py`: the `Notepad` (shared with the engine's notepad screen).
  - `brief.txt`: the base brief, as data.
- `host/features/`
  - `__init__.py`: `Feature`, `Requires`, the catalog, and its cycle check.
  - `write.py`: write: the answer decision, write steps, Markdown lettering.
  - `erase.py`: erase: rulings carried out, erasing what is pointed at, staged typed and ink erasures.
  - `markup.py`: markup: highlight, circle, underline, strike, and words in a PDF's text.
  - `inspect.py`: inspect and point: look closer, marks, render, find, page history, changes, the
    notepad; grounding `at`.
  - `charts.py`: chart, calendar, posts.
  - `search.py`: search: the step and the tool, the search provider's client, the encyclopedia lead.
  - `pictures.py`: pictures, image, coloring, picture_edit, web_picture: the image slot through the
    engine, a picture placed as strokes or inserted, picture search.
  - `draw.py`: draw: figures, elements, edits, undo.
  - `games.py`: chess, adventure, messages: starting a game, and a game page's turn.
  - `notebook.py`: notepad, tag: the notepad tool, the wipe step, the tag step.
- `page/`
  - `__init__.py`: snapshots, provenance, the safe area, page history, device-style erasing (`rm_page`,
    `rm_erase`).
  - `render.py`: a page to PNG (`rm_render`).
  - `typed.py`: typed text: reading, layout, records (`rm_typed`, `typed_layout`, `typed_records`).
  - `images.py`: pictures placed on a page (`rm_images`).
  - `marks.py`: numbered marks and arrows (`rm_marks`, `rm_arrows`).
  - `pdf.py`: a PDF page's text, and PDF documents (`rm_pdftext`, `rm_pdfdoc`).
- `draw/`
  - `__init__.py`: `Drawing` and pens: geometry to strokes, written to a page (`rm_art`).
  - `lettering.py`: the monoline font, its serif set, and numbers as paths (`rm_text`, `rm_serif`,
    `rm_glyphs`).
  - `shapes.py`: solved elements, the daemon's signature, curve helpers, SVG path parsing
    (`rm_elements`, `rm_sig`, 100 lines of `coloring_pages`, `parse_path` from `rm_chart_strokes`).
- `charts/`
  - `__init__.py`: validate, compile to Vega-Lite, render, the lettering font, the icon helpers (the
    compile and render sections of `rm_chart`, and `rm_font`).
  - `spec.py`: chart types, what each can do, validation.
  - `numbers.py`: quantities and distributions: bar, line, area, scatter, pie, histogram, waterfall,
    candle, stock, bullet, slope, bump, radar, ridgeline, gauge, funnel, waffle and the rest of that family.
  - `structure.py`: parts and relations: treemap, marimekko, sankey, venn, tree, flow, matrix, quadrant,
    maps.
  - `plans.py`: plans and lists: kanban, agenda, checklist, habit, timeline, gantt, journey, clock,
    progress, cards.
  - `calendar.py`: the month and the week: grid, pills, haiku cards, weather rows.
  - `almanac.py`: weather, holidays, on-this-day facts, geocoding (`rm_weather`, `rm_holidays`,
    `rm_history`, the host's geocoder).
  - `posts.py`: social post cards and their feeds (`rm_reddit`, `rm_social`, the host's feed code).
  - `icons.py`: the generated icon outlines (`rm_icons`, unchanged).
  - `strokes.py`: a chart as pen strokes from its SVG (`rm_chart_strokes`).
  - `tabletop.py`: tabletop specs to Vega-Lite, and their schema (`rm_tabletop`, `rm_tabletop_schema`).
- `games/`
  - `__init__.py`: game pages: dispatch, reading the player's writing (`rm_games`).
  - `chess.py`, `adventure.py`, `messages.py`: one game each.
  - `characters.py`: character profiles and the roster (`rm_characters`).
  - `table.py`: who sits at a game, feelings, memories, and the optional behavior pack (`rm_table`,
    `rm_residents`, `rm_cast`).
- `games/faces/`
  - `__init__.py`: the face kit and drawn portraits (`rm_faces`, `rm_faces_portraits`). It imports its
    part modules by name, in place of today's file glob (`rm_faces.py:832-841`), and the characters'
    cache key reads the package's files in place of the glob at `rm_characters.py:905`.
  - `people.py`: heads, hair, finer features, habits, clothes (`rm_faces_folk`, `rm_faces_fine`,
    `rm_faces_habits`, `rm_faces_wear`).
  - `creatures.py`: animals and machines (`rm_faces_beasts`, `rm_faces_machines`).
- `decompose/`, moved last and together with the decomposer work:
  - `__init__.py`: the one call (`rm_model`).
  - `fast/`: the C stages and their Python face (`fastdecomp`, as that work leaves it).
  - `reference/`: the Python reference, its code unchanged except import lines: `rm_paint`, `rm_lean`,
    `rm_regions`, `rm_raster`, `rm_flow`, `rm_trace`, `rmb_geometry`, `rmb_lineart`, `rmb_npops`,
    `rmb_params`, `rmb_resolution`.

The five face modules that nothing imports by name (`beasts`, `fine`, `habits`, `machines`, `wear`) are
loaded by `rm_faces`' plugin glob and register their parts on import. They are live and keep every part.

**The count.**

| | Today | After |
|---|---:|---:|
| Engine modules | 35 | 27, and 6 harness data files |
| Pipeline modules outside the decomposer | 56 | 50 (seven packages and `daemon.py`) |
| of which the 52 smaller modules | 52 | 26 files |
| of which `rm_host`, `rm_plan`, `rm_steps` and `rm_chart` (13,661 lines) | 4 | 25 files: host 8, features 11, chart families 6 |
| The decomposer: reference, C wrappers, the one call | 19 | 18, and 2 package markers (`rm_lineart` deleted) |
| Total Python files | 110 | 97 |
| Flat `rm_*.py` | 61 | 0 |

Before cleanup the largest files would be `games/adventure.py` (1,871), `games/faces/people.py` (1,800),
`charts/calendar.py` (1,472) and `games/chess.py` (1,417); every host file is under 1,000.

*Alternatives:* one package per old module (rejected: it keeps the file count and only adds folders);
moving everything at once (rejected: no step could be proven equal on its own); re-export shims during
the moves (rejected: they outlive their purpose and hide which import is real).

### 2. Objects where there is state

State lives in a few classes; everything stateless stays a plain function (raster math, geometry,
layout, chart builders, lettering, the C wrappers).

```python
# engine: paperdaemon/harnesses/__init__.py
class Harness:                    # one model family's data; shipped and user harnesses alike
    id: str; name: str; kind: str                 # "text" | "image"
    extends: str | None; patterns: tuple; refuse: tuple
    fields: dict                  # capabilities and parameters, by harnesses.schema
    request: dict                 # extra request fields, keyed by a capability's value
    workflows: dict               # image harnesses
    features: dict                # {"off": [...]}: may narrow what is offered, never widen it
    decision: dict                # e.g. {"inspect_tokens": 12000}
    assists: list                 # empty in every shipped harness
    def matches(self, hint) -> bool
    def offer(self) -> dict       # an image harness, as the text model is told about it

class Registry:                   # loads shipped/*.json and the user's folder with one loader
    def get(self, harness_id) -> Harness
    def guess(self, kind, hints) -> Guess          # (harness, which hint, the hint)
    errors: list                                   # files that did not load, with the reason

# engine: paperdaemon/models/lineup.py
class Slot:                       # one model of a lineup
    role: str; location: str; script: str; api: str; model: str
    harness: Harness; overrides: dict; tested: dict
    def capabilities(self) -> dict                 # override > accepted test > harness > default

class Lineup:
    name: str; text: Slot; image: Slot
    def facts(self, settings) -> Facts             # what feature requirements are checked against
    def activate(self, settings, catalog) -> RunFile   # resolves features, writes <data>/run/lineup.json

class FeatureSet:
    @classmethod
    def resolve(cls, catalog, facts) -> "FeatureSet"   # in dependency order
    def state(self, name) -> State                     # on | degraded | off, because, missing
    def to_json(self) -> dict

# host: paperdaemon/pipeline/host/job.py
@dataclass
class Item:                       # one listed thing: para:N, line:N, mark:N or picture:N
    id: str; kind: str; text: str; box: tuple; owner: str; made: dict; new: bool

@dataclass
class Page:
    doc: str; number: int; page_id: str; items: dict
    pdf: object; text_column: tuple; safe_area: tuple; sha: str; history: list

@dataclass
class Ruling:
    item: str; is_: str; then: str

@dataclass
class Step:
    id: int; kind: str; what: str; fields: dict; answers: list; replaces: str | None
    status: str; note: str; place: str | None

@dataclass
class Decision:
    kind: str; steps: list; rulings: list; note: str

class Job:                        # replaces the JOB dict's 64 keys
    page: Page; draft: "Draft"; decision: Decision; steps: list
    outcome: str; note: str; record: dict          # phases, timings, refusals, warnings

# host: paperdaemon/pipeline/host/commit.py
class Draft:
    def stage(self, why, strokes=(), typed=(), pictures=()); def unstage(self, op); def hidden(self)
    def commit(self, page) -> CommitResult; def verify(self, page) -> list

# host: paperdaemon/pipeline/host/__init__.py
class Host:
    def __init__(self, run: RunFile, model: ModelClient, catalog: Catalog)
    def serve(self)                                  # the queue loop
    def run(self, job) -> Outcome                    # read, decide, steps, commit, verify, record
    def turn(self, messages, tools, force) -> Call   # stopped by tokens and repetition only
    def decide(self, job) -> Decision                # decision.py
    def route(self, step, job) -> StepResult         # the step's feature

# host: paperdaemon/pipeline/host/features/__init__.py
@dataclass(frozen=True)
class Requires:                   # every field empty unless a feature names it
    text: dict                    # capability -> value or minimum, e.g. {"vision": True}
    image: tuple                  # abilities, e.g. ("generate",)
    workflows: tuple              # image workflows, e.g. ("childrensColoringBook",)
    search: bool                  # a search provider is configured
    content: tuple                # installed content, e.g. ("characters",)
    settings: tuple               # filled settings, e.g. ("location",)
    features: tuple               # other features, by name

class Feature:
    name: str; summary: str
    requires: Requires; optional: Requires
    steps: tuple                 # step kinds it adds to the plan's enum
    tools: tuple                 # tools it serves during its steps
    decisions: tuple             # decision names it declares, for assists
    def brief(self, ctx) -> str                    # its section of the brief, static per lineup
    def schema(self, ctx) -> dict                  # its step fields and tool schemas
    def validate(self, step, job) -> list[str]     # validity only
    def execute(self, step, job, host) -> StepResult

class Catalog:                    # every Feature subclass, by name
    def check(self)               # unknown names and cycles are refused at startup
    def to_json(self) -> dict     # the requirements, as the engine and the Models screen read them
```

A feature's requirements are class data. The engine reads them by importing
`paperdaemon.pipeline.host.features`. The feature modules import their heavy dependencies inside
`execute()`, and a unit test proves that importing the catalog loads nothing beyond the standard library
and the catalog itself. *Alternative:* a separate `features.json` (rejected: two definitions of one thing
that would drift).

### 3. The feature list

| Feature | Adds | Hard requirements | Optional (degrades without) |
|---|---|---|---|
| write | the answer decision; the `write` step; `write_paragraph`, `write_line` | | |
| erase | erasing by ruling; an `erase` step that points in words | | feature point (no erasing by pointing) |
| inspect | `look_closer`, `show_marks`, `render`, `page_history`, `changes`, `notepad_read` in the decision turn | | text: vision (without it: text views only, no images) |
| point | `at` on any step; `find` | text: vision | |
| markup | `highlight`, `circle`, `underline`, `strike` steps | | feature point (no marking what an arrow points at) |
| draw | the `draw` step; `draw_figure`, `element`, `edit_figure`, `undo_last` | | text: vision (no look-and-fix rounds; they are off by default) |
| chart | the `chart` step and tool | | |
| calendar | the `calendar` step; the `history` tool | feature chart | settings: location (no forecast or sunrise; holidays and facts stay) |
| posts | the `posts` step (social cards) | feature chart | |
| search | the `search` step; `web_search` | a search provider | |
| pictures | placing a picture as strokes or inserted, and new pages (used by the picture features) | | |
| image | the `image` step and tool | image: generate; feature pictures | |
| coloring | the `coloring` step | image: generate; feature pictures | image workflow `childrensColoringBook` (the subject goes as a plain prompt, and the job's log says so) |
| picture_edit | `source: picture:N` on image steps; reference workflows | image: edit_reference; feature image | |
| web_picture | the `web_picture` step | features search and pictures | |
| chess | the `chess` step; chess page turns | content: characters, the chess engine | text: vision (no written moves; the player moves pieces) |
| adventure | the `adventure` step; adventure turns | | feature image (no scene pictures), feature picture_edit (scenes drawn afresh), text: vision |
| messages | the `messages` step; chat page turns | content: characters | feature image (no pictures in the chat), feature picture_edit (no pictures from a resident's face), text: vision |
| notepad | the `notepad` tool | | |
| tag | the `tag` step | | |

The decision itself (skip, answer, plan), `need_step`, and the rulings belong to the host, not to a
feature. Every feature needs the text slot, which the loop already requires before it starts.

**Requirement kinds.** The four the maintainer named: text capabilities (`vision`, `forced_tool`,
`context` at least N), image abilities (`generate`, `edit_reference`, `img2img`, `inpaint`) and
workflows, a search provider, and other features. This design adds two, for the maintainer to confirm
(Open Questions): installed **content** (the characters, the chess engine) and a filled **setting** (the
location).

**Resolution.** When a lineup is activated (`loop.activate`, and on every engine start), the engine
builds the facts:

- the text slot's effective capabilities;
- the image harness's abilities and workflows, or none when the image slot is empty;
- whether a search provider is configured;
- which content is installed and which settings are filled;
- the features the user switched off in settings, and those the text harness's data turns off.

It resolves the catalog in dependency order. A feature is **off** when a hard requirement is missing, a
required feature is off, the user switched it off, or the harness turns it off. It is **degraded** when
an optional one is missing, and **on** otherwise. Each off or degraded feature carries its reasons as a
chain, for example:

    coloring: off because image is off because the image slot of "Qwen 3.8 + Klein" has no location
    web_picture: off because search is off because no search provider is configured

A cycle in the catalog is refused when the engine starts and when the tests run, naming the cycle.

**The run file.** `<data>/run/lineup.json` replaces `run/harness.json` (`RM_HARNESS`) and the `RM_LLM_*`
variables. It holds the lineup's name; the text harness's data (capabilities, request data, brief
additions, decision settings, assists); the image offer; the resolved features with their states and
chains; and the settings the host needs (location, output folder, search, the chart and calendar
options). The host reads settings only from it. The environment keeps the wiring: state folder, mirror,
engine address, token. The engine restarts the host when the file's content changes, as it does today
when the harness values change.

**The host's side.**

- The brief is the base text, the harness's additions, one section per enabled feature (a degraded
  feature's section leaves out what it lost), and the notebook's prompt last, word for word.
- The tool schema is the decision tools plus each enabled feature's tools. The plan's `do` enum lists
  only the enabled step kinds.
- Both are rendered once per run file, so the cached prompt prefix holds from job to job.
- A step whose kind belongs to a disabled feature is refused before it runs, with the chain, and the job's
  record keeps the refusal.
- The engine's card still refuses a picture edit the image harness cannot do, as the last backstop.

**The Models screen** shows, for each lineup, every feature with its state, and the chain for each
off or degraded one (`GET /api/v1/lineups/{name}/features`).

*Alternatives:* resolving features per job in the host (rejected: the prompt prefix would change from job
to job, and the screen could not show what a job will be offered); keeping hard-wired capability checks
in the brief (rejected: they cannot express one feature needing another).

### 4. Harnesses are data

A shipped harness becomes a JSON file in the format user harnesses already use, and both load through
one loader with the same rules (`harnesses/schema.py`). For example:

```json
{
  "id": "qwen3.8-27b",
  "name": "Qwen 3.8 27B",
  "kind": "text",
  "extends": "default-text",
  "patterns": ["qwen-?3\\.?8-?27b"],
  "refuse": ["(^|-)base(-|\\.|$)"],
  "context": 65536,
  "request": {"thinking": {"off": {"chat_template_kwargs": {"enable_thinking": false}}}}
}
```

- `request` replaces the last code hook, `tune()` (today the `QwenTemplate` mixin). When a capability
  has the named value, its fields are merged into every chat request. The engine's adapter applies it,
  and the host never sees it.
- A text harness's other data: `brief_additions`; `decision` (the inspection budget, whether the
  decision tool call is forced); `features.off`; `assists`.
- An image harness keeps its steps, ranges, sampler, size, abilities and workflows, as today.
- A harness may narrow what the host offers (switch features off, add assists). It never loosens
  validity: there is no per-harness `validate()`.

The add-model-slots-and-harnesses design rejected data harnesses because two hooks were code. Neither is
code any more: `tune` becomes `request`, and the picture prompt became workflows.

### 5. The model decides; the host checks validity

**The decision turn's schema.** The tools stay `plan`, `answer` and `skip`. Each nested object declares
only its required keys, in the order a model writes them, because llama.cpp's tool grammar drops or
respells a key written out of declared order. The other keys are free and documented in the
description.

```
plan(steps, rulings)        answer(answers, lines, rulings)        skip(note)

rulings: [{id, is, then}]               keys required, in this order; every item new since the last job
                                        must be ruled, and any other listed item may be
  id    one of the listing's ids (a static enum: para:1-30, line:1-40, mark:1-99, picture:1-12)
  is    request | command | asked_to_remove | stale_work | question | conversation | note | other
  then  erase | keep

steps: [{do, what, answers}]            required, in this order
  do       one of the enabled features' step kinds
  answers  the ids this step carries out ([] for a step nothing on the page asked for, such as a lookup)
  ...      each feature's own fields, any order: replaces (picture:N), quote (the user's words naming a
           number or a tag), source, search, sort, period, pictures, count, site, workflow, steps,
           seed, target, words, color, strength, opponent, members, at, size, near, side
```

`answer`'s `answers` (ids) replaces its free-text `task`. The notepad's "asked" line is built from the
answered items' text.

**Inspection before ruling.** The `inspect` feature puts its tools in the decision turn:

- `look_closer(id | box)`: a close view, or the item's text and readings for a model without vision;
- `show_marks(detail)` and `render()`;
- `page_history(back)`: the page as an earlier job found it;
- `changes()`: what was added and erased since the last job;
- `notepad_read(scope)`: this page's or the notebook's entries, beyond the window the intake shows;
- `find(what)`, from `point`.

The turns are bounded by tokens and repetition, never by a clock:

- the harness's `decision.inspect_tokens` counts what the inspections add and what the model writes
  (default 12,000);
- the same call with the same arguments is refused as already shown;
- once the budget is spent, only `skip`, `answer` and `plan` remain on offer.

**Validity, the host's whole say.** A refusal goes back to the model as a turn that says what to fix. It
is never a silent rewrite.

1. Every id the decision names exists on this page.
2. Every item new since the last job has a ruling, in a plan or an answer.
3. Rulings are consistent:
   - `then: erase` only with `is` request, command, asked_to_remove or stale_work;
   - `stale_work` only on this system's own items.
4. A step's kind belongs to an enabled feature; its fields are ones the feature declares. A degraded
   feature refuses the fields it lost.
5. Legal moves: a game's moves by its rules; tools in the order a step allows.
6. Layout: places inside the safe area, never overlapping; a refusal gives the numbers.
7. Citations: a `quote` must be found (whitespace and case normalized) in the notebook's prompt, the typed
   text or the reader's reading of the user's ink, and must contain the value it vouches for (a tag's
   name, a step count, a seed).
8. `replaces` names a picture this system made, and no two steps replace the same one.
9. Capabilities: no image to a model without vision; no edit the image harness cannot do (the card
   refuses it again).
10. A ruled request comes off only once every step that `answers` it has landed. A failed step keeps the
    request on the page, as today.

**The word-matching checks, and what replaces each.** Line numbers are in `pipeline/rm_host.py` unless
another file is named.

| # | Where | What it decides today | The incident or behavior it protects | Replaced by |
|---|---|---|---|---|
| C1 | `_WEB_CUE` :2565, applied :3652 | an `image` step whose words name a site or "the web" becomes `web_picture` | pictures asked for from a named site were planned as generated ones; the image model painted three pictures nobody asked for | the step kind is the model's: `do` is an enum, `image` (generate) and `web_picture` (find) described apart |
| C2 | `_FACT_CUE` :2482, `_PIC_CUE` :2484, applied :3659 | a `web_picture` step that asks for facts or news becomes `search` | on-this-day facts were planned as a web picture, and an unrelated web image was traced onto the page as about 64,000 strokes | the same enum; `web_picture` is described as pictures only |
| C3 | `_MARKUP_DRAW` :2560, applied :3665 | a `draw` step reading "circle / underline / line through X" becomes circle, underline or strike, with X as its target | a circle around a word, planned as a drawing, came out round and too small for the word | the mark-up kinds in the enum; the markup step's `target` and `words` |
| C4 | fold at :3679, with `_reddit_ref` :2609 and `_reddit_query` :2649 | several `web_picture` steps from one subreddit fold into one posts step (count up to 4) | a subreddit's top pictures became cards placed one by one | a `posts` step with `count`; the model chooses |
| C5 | `_CHART_CUE` :2485 and the calendar words at :3695, applied :3694 | an `image` or `draw` step naming a chart, calendar or map becomes `chart` or `calendar`, or is dropped when the plan already has one | an image step for a weekly weather calendar, planned beside the calendar step, sent the card to the image model for nothing and failed the job | the enum; the incident becomes a case |
| C6 | `_changes_picture` :2526, with `_CHANGE_CUE` :2491, `_CAL_STRONG` :2499, `_CAL_WEAK` :2500, `_CHART_DEF` :2503, `_PRONOUN` :2504, `_REF_STOP` :2505; applied to the step's words :3734 | a step whose words change a chart or calendar this system made becomes a redo of it (`near: picture:N`) | a request to add events to the calendar on the page was planned as a search and a list written over the calendar | `replaces: picture:N`, chosen by the model, which sees each picture's spec in the listing |
| C7 | :3741-3747, the page's single request read by `_is_request` :4681 and `_changes_picture` | the same, judged by the request's words when the step's own words do not say | as C6 | as C6 |
| C8 | :3840: `_sweepable` :4821, built on `_is_request` :4681 (`REQUEST_VERBS` :4666), `_carried_out` :4737 (`_ASKS` :4708, `_WORD_THINGS` :4719, `_GENERAL` :4723, `_STOPWORDS` :4724, `_MAKING` :4729) and `_redoes` :4803 (`_REDO_ONLY` :4799) | at plan time, adds an erase of every typed paragraph that reads as the request this job carries out, named by the model or not | the model planned the work and forgot to erase the request; an earlier, wider sweep also took the user's own to-do lines that open with a work verb | rulings on every new item; the host checks completeness, not meaning; validity rule 10 |
| C9 | :3856, the same test on lines of handwriting as read | the same, for handwritten requests | a handwritten request's last word stayed when the model named four of its five marks | a ruling on `line:N`, one id for the whole line |
| C10 | `_auto_erase_requests` :4961, test at :4982 | after every step succeeds, erases any paragraph that reads as the carried-out request | as C8 | as C8 |
| C11 | `_is_question` :4653, applied :5043 | keeps a paragraph ending in a question mark, unless it reads as a request dressed as a question, whatever the model ruled | the model erased a question together with the instruction, and the answer lost its context | `is: question` with `then: keep` (rule 3); the model rules |
| C12 | `_is_request(confirm=...)` :4681 with `REDO_VERBS` :4677, applied :5047 | in a job that only writes words, keeps a paragraph the model called a request unless one of its sentences opens with a work verb | a complaint about an earlier answer was labeled a request and erased | `is: conversation` with `then: keep`; `changes()` and `notepad_read()` show what is new and the earlier reply before the model rules |
| C13 | `_erase_ink_saying` :5196: quote extraction :5209, the word "arrow" :5270 | erases ink by what it says, and adds the arrow drawn from it when the description contains the word "arrow" | grounding a whole description took the word the arrow pointed at as well | ids: lines and marks are listed with their readings and arrows with their mark ids; the model names them; `at` for what has no id |
| C14 | `_reddit_query` :2649, with `_RD_SORTS` :2625, `_RD_PERIODS` :2628, `_RD_SUBJ` :2633, `_RD_FRAME` :2634, `_RD_SOURCE` :2639, `_RD_LISTING` :2641, `_RD_PICS` :2646; used :2795, :2897, :2988 | strips sort, period, source and asking words from a Reddit search, and infers the sort and the period | the feed ranks every word it is given, so asking words pulled in unrelated posts | the posts step's fields: `source`, `search` (the topic's words only), `sort` and `period` (enums), `pictures` |
| C15 | `_reddit_ref` :2609, used :2793, :2896, :2987 | the subreddit, sort and period named in free text | as C14 | as C14 |
| C16 | :1530 (`web_search` reroutes to `_reddit_search` :2891 when the query names Reddit), :2898, :2988, :2797, :2996 | routes a search or a picture fetch to Reddit by the word "reddit"; picture words turn on picture posts; a plural picture word makes a card of four | a web search for a subreddit's top posts took four turns and returned stale items; pictures asked for on Reddit came back as one traced web picture | the model picks the `posts` step; `web_search` never reroutes; `count` is a field |
| C17 | `_site_in` :2577 (`_SITES` :2570), used :2943, the "from the X" strip at :2946 | the site to search for pictures on, from a domain or a site's name in the words | a picture asked for from a named site was searched on the whole web | the `web_picture` field `site` |
| C18 | `_user_numbers` :2143, then `models/slots.py` `numbers_in` :147 and `picture_steps` :155 | a step count is the user's (not clamped) when the same number appears in the prompt, the typed text or the read ink | the user's own step count, above the model's range, is used as written; the model's own choice stays in the harness's range | `steps` with `quote`: the model quotes the user's words; rule 7 checks the quote |
| C19 | `_stage_tag` :4202, test at :4213 | a tag only when its name appears in the notebook's prompt or on the page | the model never tags a page on its own | kept as validity, as a citation: the tag step carries `quote`; rule 7 |
| C20 | `_WIPE_TYPED` :1411, `_WIPE_READ` :1412, `_leading_slash` :1415, `_wipe_command` :1431 | finds `/wipe`, typed or handwritten (a slash read as `/`, `\|`, `I`, `l` or `1`, or as a thin stroke of its own), with no model turn | the user's command to empty the notepad | removed, typed and handwritten, with the `wipe` step: a notepad is emptied from the Notepads screen |
| C21 | `_repeats_old_reply` :1373, used :710, :826 | refuses a reply 85% the same as the reply this system already wrote on this page | asked to continue a role-play, the model wrote its previous turn again, word for word | removed: `changes()` and `notepad_read()` before ruling, and `answers` must name the new items |
| C22 | `_MONTHS` :6990, read at :7005-7006 in `_calendar_facts` :6994 | the month or week of a calendar step, from its words | facts written from memory had wrong dates, so the host fetches the dates' facts and needs the month | the calendar step's `what` is `YYYY-MM` or `week`, a checked format |
| C23 | `_run_game` :7348, at :7356, :7368, :7385 | which game a game step starts (adventure, messages, chess), and refusing other games, by words | one `game` step for every game | the step kinds `chess`, `adventure`, `messages`, each a feature; a game not in the enum cannot be asked for |
| C24 | `pipeline/rm_steps.py:129-130` in `build` :123 | a bare-string step becomes an erase when `erase_targets` finds anything, which for any non-empty text it always does | a latent defect: every bare-string step is an erase | steps are objects; a bare string is refused |
| C25 | `pipeline/rm_steps.py`: `ALIASES` :65, `LEGACY` :86, `_do` :106, `_what` :112 | the model's other names for step kinds and fields | the model mixed field names on one-step jobs | the `do` enum and declared fields; the alias table becomes an assist kind for a weaker model's harness |
| C26 | `pipeline/rm_steps.py:279-291` (`_PARA`, `_LINE`, `_MARK`, `_MARK_RANGE`, `_PIC`, `_INK`, `_ALL_INK`), `erase_targets` :296 | erase targets in free text ("mark 3 and mark 4", "all ink", words) | an erase written as prose matched nothing, and the request stayed | ids from the enum and `at`; free text is refused |
| C27 | `pipeline/rm_steps.py`: `_LOCATED` :344, `named_words` :348, `located_words` :356 (used at :3329) | "the word X in para:N" means the words, not the paragraph | highlighting one word highlighted the whole paragraph | the markup step's `target` (an id) and `words` (the exact words within it) |
| C28 | `pipeline/rm_games.py:593-594` in `choose_setup` :588 | the chess strength (a 3- or 4-digit number) and the player's color, from the request's words | setup without asking | the chess step's `color`, `strength` and `opponent` |
| C29 | `pipeline/rm_messages.py:238-239` in `pick_members` :227 | a chat's members by matching names before asking the model | setup without asking | the messages step's `members` (ids from the installed roster) |
| C30 | `pipeline/rm_messages.py:484` | a resident's picture is of itself (edited from its face) when its words say "me", "myself" or "selfie" | a resident's own face kept from picture to picture | the resident's picture request carries `of: self` or `of: other` |

**Host rewrites that decide intent without matching words.**

| # | Where | What it does today | Becomes |
|---|---|---|---|
| S1 | :3756-3772 | a calendar step redoes the calendar this system made, whatever the plan said | the model's `replaces` |
| S2 | :3776-3789 | a second calendar of this system's that no step redoes is erased as stale | the model's ruling `stale_work` |
| S3 | :3793-3808 | a new picture takes the place of a picture the plan erases | kept: placement is the host's |
| S4 | :3812-3824 | two steps that change one picture fold into one | rule 8: refused with a turn |
| S5 | `_keep_requests` :4925, `_unsweep` :4949 | a failed content step keeps the requests | kept, as rule 10, tied to `answers` |
| S6 | `_stale_assets` :4895 | this system's ink more than 40% inside a new content box is erased | the model's `replaces` or a `stale_work` ruling |
| S7 | `_ink_on` :4875 | this system's ink on a picture being erased goes with it | kept: what this system drew on its own picture |

**Every incident becomes a test case.**

- A unit case in `tests/test_decisions.py` for each row (C1 to C30, S1 to S7). Each holds the listing as
  the host builds it, a recorded decision, and what the host must do with it: refuse it with a turn,
  erase this, keep that. These guard the host's code.
- A benchmark case for each row that needs the model's judgment (C1, C2, C3, C5, C6, C8, C11, C12, C21):
  a fixture page in `tests/benchmark/cases`, so every lineup's rulings are measured on real runs.

*Alternatives:* keeping the checks beside the rulings as a safety net (rejected: two deciders that
disagree silently, tuned on the phrasing they were fixed for, and able to overrule the notebook's
prompt); a period in which the checks only log their disagreements (rejected: machinery that outlives
its use; the cases measure the same thing).

### 6. Keyword assists

A harness may carry assists, so a weaker model can be helped by data, not code. Each assist names one
decision from the closed list the features declare, for example `step.kind`, `step.replaces`,
`item.ruling`, `markup.target`, `posts.source`, `image.steps`. It also says which text it reads, what
fires it (keywords, as whole words with case ignored, or the text's last characters), an optional
condition on the model's value, and either a `hint` (preferred) or a `set` (an override):

```json
"assists": [
  {"decision": "step.kind", "reads": "step.what", "when": "image",
   "keywords": ["the web", "online", "website", "real photo"],
   "hint": "This step names the web. A picture that already exists is a web_picture step."},
  {"decision": "item.ruling", "reads": "item.text", "ends_with": "?", "when": "erase",
   "set": {"is": "question", "then": "keep"}}
]
```

- A hint that fires and disagrees with the model's value goes back as one turn, counted in the decision's
  budget. The model keeps its choice or changes it.
- An override sets the value, and the job's record says which assist did it.
- Assists run after the model's decision, never in place of it.
- No shipped harness carries any. `harnesses/examples/keyword-assists.json` carries the old word lists
  as an inactive example.

### 7. One model client, no clock

The host's turns go to the engine (`/host/chat`), which speaks the slot's API family through
`models/adapters.py` and applies the harness's `request` data. The adapter streams every call, including
the three that are unstreamed today. The runaway guard (token limit, repetition) moves with it. No model
call has a timeout. A call ends when the reply ends, when the guard stops it, or when the engine reports
that the server's process has exited.

A job's turns are bounded the same way: the harness's `decision` data holds the token budget and a
ceiling on turns, in place of the hidden `RM_HOST_TURNS`. Waiting for a server to start uses the engine's
readiness, as hot swap already does, never a clock. The
host's own HTTP client (`chat`, `_ask`, the grounding calls) goes, and a text slot with `api: anthropic`
can run jobs.

### 8. One settings schema

`settings.SCHEMA` lists every setting once: its path, type, default, range or choices, label, help text,
and whether it is a secret (secrets go to the credential store). From it:

- `load()` fills defaults;
- `validate()` gives every error, in one wording;
- `GET /api/v1/settings/schema` serves it, and the UI's forms take their ranges, choices, labels and
  messages from it, in place of the rules restated in `network.js` and `tablet.js`.

The capability rules for slots stay in `harnesses/schema.py`, which the settings schema references for a
slot's overrides. The hidden settings join the schema as the maintainer decides (Open Questions):
`RM_CALENDAR_MODE`, `RM_CHART_PATH`, `RM_OUTPUT_FOLDER`, and the features the user switches off.
There are no street maps and no map key. Developer switches are listed in one module, and the
leftovers go.

### 9. Build and dependencies

- `tools/build_app.py` first builds the C decomposer with `fastdecomp/build.py`: `--generic` for a build
  that is shared or published, native for a build used on the machine that made it. A failed C build
  stops the app build.
- Once the single C decomposer call is finished, a test imports the engine, the daemon, the host and
  `studio` in fresh interpreters. It asserts that none of OpenCV, numba, llvmlite, SciPy, scikit-image or
  Shapely is loaded.
- When that test passes, the five packages move from `[project].dependencies` to a `reference`
  dependency group, with their exact pins kept (the reference's identity depends on them). The `dev`
  group includes it, and `build_exe.py` stops collecting them.
- Today the test would fail on two counts: the fast path imports SciPy (`rmpaint_fast.py`, and `rmb_npops`
  through `rmfast.py`), and `rm_chart_strokes` and `studio` use `rm_paint`'s preview renderer and Lab
  conversion. The first is the decomposer work's to finish. The second needs the maintainer's choice
  (Open Questions).

### 10. Comments say what and why

Comments and docstrings say what code does and why. The incident narratives move out of the code: each
incident's lesson stays as one line of why, and the incident itself becomes a test case (decision 5).
American spelling, no names, no dates.

## Migration Plan

Small steps, each independently testable. Every step keeps these gates green:

- **G1 unit:** `uv run pytest` passes: 193 today, plus the tests the step adds.
- **G2 publish:** `tools/publish_check.py` exits 0, and `node tools/check.mjs` is clean. Today the latter
  exits 1 on one finding: python-chess's own method name, called at `rm_chess.py:394`, which cannot be
  renamed; step 3 teaches the check to allow that call.
- **G3 prefix:** the host's brief and tool schema are byte-identical to the recorded copy (structure-only
  steps).
- **G4 replay:** the model replies recorded at the baseline benchmark run, replayed through the host with
  the model stubbed, commit byte-identical pages. This is a refactoring guard only, never behavior
  evidence.
- **G5 goldens:** every chart type's sample spec renders the same PNG bytes, and every face of a sample
  roster the same SVG.
- **G6 benchmark:** with the maintainer's go-ahead, the benchmark on the default lineup passes the cases
  it passed at the baseline.
- **G7 identity:** the decomposer identity check passes. It runs whenever a step touches the decomposer
  or a module it imports.

Steps:

1. **Baselines.** Record the test count, the benchmark on both shipped lineups, the host's prefix, the
   replay transcripts, the goldens, and which modules each process imports (G1, G6).
2. **Build.** `build_app.py` builds the C decomposer first (G1; the built app starts).
3. **Dead code out.** The measured list, and whatever of the unreachable list the maintainer approves.
   Also: unused imports, the host's docstring in its place, developer commands down to the two entry
   points (G1, G2, G3, G4).
4. **Settings schema.** The schema, its route, schema-driven validation and forms, and the hidden
   settings classified (G1; each settings screen rendered headless).
5. **One paths module, one ledger, one notepad** (G1, G4, G6).
6. **One sync client, one token module, `library.py`.** Merged function by function, with a test for each
   merged function and a dry-run push of a fixture page (G1, G6).
7. **One reader.** The host reads ink through `paperdaemon.reader`; `rm_ocr` goes. The readings of the
   fixture pages are compared before and after (G1, G6).
8. **`page/`.** `rm_render` stays flat until step 16, because the reference imports it (G1, G3, G4, G6).
9. **`draw/`.** `rm_art` stays flat until step 16 for the same reason (G1, G4, G5).
10. **`charts/`** (G1, G4, G5).
11. **`games/` and `games/faces/`** (G1, G4, G5).
12. **`daemon.py`, and both processes started as modules.** `--run-pipeline` takes a module name (G1;
    G6; the built app starts both processes).
13. **`host/`, structure only.** The models replace the `JOB` dict; then `Host`, `layout`, `job`,
    `commit`, `intake`, `notebook`; then the eleven feature modules one at a time, with the brief and the
    tool schema generated from them (G1, G3 and G4 after each part; G6 at the end).
14. **Harnesses as data.** The shipped JSON files, one loader, `request` in place of `tune()` (G1, G3).
15. **Features.** The catalog, resolution at activation, the run file, the host building from the
    enabled features and refusing disabled steps, the Models screen panel. Settings reach the host only
    through the run file. This changes behavior (G1; G6 on both shipped lineups and on a lineup with no
    image slot).
16. **`decompose/`,** once the single C call has landed, together with that work: `rm_model`,
    `fastdecomp` and the reference move; `rm_render` moves into `page/render.py` and `rm_art` into
    `draw/__init__.py`; only the reference's import lines change (G7 on the full corpus, G1, G6).
17. **Dependencies.** The import test; the `reference` group; `build_exe.py` stops collecting the five;
    the app's size recorded before and after (G1; the built app runs G6).
18. **One model client.** The host's turns go through the engine's adapters, with no clock. This changes
    behavior: an Anthropic text slot can run jobs (G1, G6).
19. **The decision schema.** The `do` enum from the features; objects only (C24); free-text erase targets
    and aliases go (C26, and C25 as an assist kind); `rulings`, `answers`, `replaces`, `quote`; the
    validity rules, each refusing with a turn (G1 with a test per rule; G6).
20. **Keyword assists.** Their schema, hint and override, and the inactive example (G1).
21. **Inspection turns.** In the decision turn, with the token budget and the repetition refusal (G1 with
    a stub that loops; G6).
22. **Plan rewrites go:** C1-C5 and C23 (G1; G6 with the new cases; a real run).
23. **The redo family goes:** C6, C7, S1, S2, S4, S6 (as 22).
24. **The sweep and the vetoes go:** C8-C12; S5 follows `answers` (as 22).
25. **Parsing goes:** C13-C17, C22, C27 (as 22).
26. **Citations:** C18, C19 (as 22).
27. **Games:** C28-C30 (as 22).
28. **Handwritten `/wipe` (C20) and the repeated reply (C21),** as the maintainer decides (as 22).
29. **Evidence.** With the maintainer's go-ahead: both shipped lineups on the benchmark and the incident
    cases, and the maintainer's held-out pages; pass counts and times recorded beside the baseline.

Steps 2-14 are meant to change no behavior; step 7 may change how ink is read, and its comparison is
recorded. Steps 15 and 18-28 change behavior, and each is recorded with real-run evidence before
the next begins. Any of steps 22-28 can be reverted on its own.

## Risks / Trade-offs

- **[Rulings move judgment to the model, and a weaker model may rule worse than the word lists did]** →
  each incident is a benchmark case measured before its check goes; a weaker model's harness can opt into
  assists; each removal is its own step and can be reverted alone.
- **[The new fields add prompt tokens to every job]** → the schema stays static per lineup, so the
  cached prefix holds; the static prefix and per-job tokens are measured at steps 19 and 22-28 against
  the baseline (14,931 + 6,741 characters).
- **[The server's grammar drops keys written out of declared order]** → only required keys are declared,
  in writing order (`id, is, then`; `do, what, answers`); `tools/check_schema_order.py` runs against the
  real server with the maintainer's go-ahead.
- **[Inspection turns cost time]** → bounded by the harness's token budget and the repetition refusal;
  the default budget is set from the benchmark.
- **[Merging two sync clients changes sync behavior]** → 13 of the shared functions have drifted apart
  (pushing, snapshots, rollback, the state file), and `push_page`, `forget` and `prune_notepads` exist
  only in the pipeline's copy → merged one function at a time, each difference decided and tested,
  with tests and a dry-run push; the root undo record stays.
- **[The reader may read ink differently from `rm_ocr`]** → readings compared on the fixture pages; the
  ink-question benchmark case.
- **[Package moves break imports, the frozen build or the child processes]** → each move rewrites its
  importers in the same step; every module is imported in a fresh interpreter as a smoke test; the built
  app is started at steps 12, 16 and 17.
- **[Another job owns the decomposer now]** → its move is last and done with that work; G7 guards it.
- **[A feature turns off and nobody notices]** → every off or degraded feature carries its chain, on the
  Models screen and in the record of a job whose step was refused.
- **[Removing the clock lets a dead server hang a job]** → the wait ends when the engine reports the
  server's process gone or the slot not running, not after a time.
- **[The repository is public]** → incidents are described without names, page text or dates; G2 at
  every step.
- **[This change modifies requirements of changes not yet archived]** → it is archived after
  add-job-host, add-model-slots-and-harnesses, add-tool-extensions, add-engine-foundation and
  add-desktop-packaging; until then `openspec validate` notes that archiving would refuse its MODIFIED
  deltas, which is expected.
- **[The file count stays near a hundred]** → the decomposer's 18 files and the 6 harness data files are
  fixed; the rest halve. Further folding would trade cohesion for a number.

## Open Questions

Needed from the maintainer before the step that uses them:

- **`/wipe` (step 28).** Decided: removed, typed and handwritten. The Notepads screen's Wipe is the way a
  notepad is emptied.
- **The repeated reply (step 28).** Decided: the similarity check is removed.
- **`rm_paint.render` and `rm_paint._lab` at run time (step 17).** `studio.py` and `rm_chart_strokes` use
  them. Either move them into `page/render.py` and `draw/` and have `rm_paint` import them (one
  definition; an import-only edit to the reference, guarded by G7), or leave `rm_paint` untouched and
  keep a run-time copy of about 80 lines.
- **Deletions that need a word (step 3).** `rm_lineart.py` (390 lines, the readable twin of
  `rmb_lineart`, imported only by the host's unused import); `coloring_pages.py`'s four hand-drawn pages
  (768 lines) with `rm_wxicons.py` (176).
- **Where the reference lives once it is test-only (step 17).** Shipped in the app, as the Python fallback
  when the C library does not load, or under `tests/`, not shipped? This follows the decomposer work's
  fallback decision.
- **Two environment-only options (step 4).** `RM_CHART_PATH=components` (the stroke path,
  `rm_chart_strokes`, 485 lines) and `RM_CALENDAR_MODE=document` are reachable only by environment
  variables. Settings in the schema, or removed?
- **Two more requirement kinds (step 15).** Installed content (characters, the chess engine) and a filled
  setting (the location), beside the four kinds named.
- **The host's turns through the engine's adapters (step 18).** This also makes Anthropic text slots
  work for jobs. Wanted now?
- **The decomposer identity check lives outside the repository.** Should a small corpus of public
  pictures and its check live in `tests/`, so every step can run G7 here?

Can wait:

- A future interpreter mode in which a stronger model hands back a finished page. This change removes the
  harness-protocol form of it from the specs.
- Whether the chat members' enum (the installed roster) is worth its prompt tokens, or the field should
  be free text checked against the roster.
- The default inspection budget, once the benchmark has measured it.
- The default text harness's vision and forced tool call: the spec's conservative values or the code's.
