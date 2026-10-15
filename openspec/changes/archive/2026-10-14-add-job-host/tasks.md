# Tasks

The maintainer's real pages are the held-out check; nothing here is claimed done on unit tests alone.

## 1. Context and decision

- [x] 1.1 Port the base brief to a text file and build the base harness's intake from it: harness additions, descriptions of the tasks on offer, then the notebook prompt word for word; verify the static part is byte-identical across two jobs Done: the brief and the tools, recorded and checked byte for byte across jobs (`tools/baseline.py`, `tests/baseline/prefix-*`); per lineup, only what its features allow (facelift 4.3).
- [ ] 1.2 Port the page readings (typed text, reader lines, pictures and marks, the page image) and the base harness's intake for vision and for text-only models; verify with fixture pages that a text-only job receives no image and gets numbered paragraphs and marks
- [ ] 1.3 Port the plan tool and the decision turn into the base harness's output protocol (the tool call asked for) and the Qwen 3.6 27B harness's (forced), through the slot adapters; verify a prose reply is retried once with the tool named Superseded by the facelift: harnesses are data (5.1) and the decision becomes one structured turn (group 6), still to build.
- [ ] 1.4 Run a job by the harness's protocols: the intake, each reply through the output protocol, each task by its protocol (place and draw, run and return the result, or nothing), and a finished page handed back; verify with stub harnesses that the host's part follows each protocol (unit test) Superseded by the facelift: harnesses are data (5.1) and the decision becomes one structured turn (group 6), still to build.
- [ ] 1.5 Run the harness's validate() before every commit and record what it refused; verify each of the base validate()'s refusals, and that a stricter harness's refusal blocks only what it refuses (unit test) Superseded by the facelift: harnesses are data (5.1) and the decision becomes one structured turn (group 6), still to build.

## 2. Layout and steps

- [x] 2.1 Port the layout solver and its refusals; verify with randomized layouts that places never overlap and stay in the safe area Done: `tests/test_layout_and_wipe.py` (300 randomized plans: no overlap, inside the sides and below the top; a plan that cannot fit is refused).
- [ ] 2.2 Port the step runner; verify through the base validate() that a failed step blocks what depends on it and an empty planned place goes back to the model once Superseded by the facelift: harnesses are data (5.1) and the decision becomes one structured turn (group 6), still to build.
- [x] 2.3 Dropped by the maintainer: no undo of a job; the snapshot, rollback and root-undo log are removed

## 3. Notebook prompt, notepad, cleanup, tags

- [x] 3.1 Read the `sprompt` page, place it last in the system message, cut at 10,000 characters with a record; verify with fixture notebooks Done: the tags' prompts in the Tagging tab's order, then the sprompt page last for the whole notebook, cut at 10,000 characters (`tests/test_host_lineups.py`).
- [x] 3.2 Port the notepad (entries by page identity, relabeled numbers) and `/wipe` typed and handwritten; verify "wipe" without the slash is not the command Done: one `Notepad` (`paperdaemon/notepad.py`), `/wipe` only with its slash (`tests/test_layout_and_wipe.py`), the notepads listed, read and wiped (`tests/test_api.py`).
- [ ] 3.3 Port the sweep with its listed word sets, and veto the model's erasures with the same test; verify with the pipeline's case table (to-do stays, role-play stays, written request goes) Ported; the facelift (group 8) replaces the sweep and its word sets with the decision's rulings.
- [ ] 3.4 Port the tag step with the explicit-direction check, applied at commit only when nothing failed; verify each refusal
- [x] 3.5 The maintainer's rule: a skipped job writes nothing to the notepad (was: leave skipped jobs' entries out of the notepad the model is shown, and keep what jobs made; verify with a fixture notepad that a page's earlier skips never reach a later job)

## 4. Limits and records

- [x] 4.1 Stop a turn on its token limit or on repetition, never on time; verify with a stubbed endpoint that loops Done (facelift 5.7): streamed through the engine, stopped by tokens and repetition only, no clock on any model call (`tests/test_model_calls.py`).
- [ ] 4.2 Record each job's outcome, phases, steps and durations; verify with a unit test

## 5. The notepad screen

- [x] 5.1 Add `GET /api/v1/notepads`, `GET /api/v1/notepads/{doc}` (entries with current page labels, skips marked, and the text the next job is shown, from the host's own function) and `DELETE /api/v1/notepads/{doc}`; verify with API tests on a fixture mirror and notepads, including a trashed notebook left out Done: `/api/v1/notepads`, `/api/v1/notepads/{doc}`, and wipe (`tests/test_api.py`).
- [x] 5.2 Build the notepad screen from the mockup: the notebook list, the entries with the model's window marked, the view of what the next job is shown, the wipe confirmation, and entries arriving as jobs finish; verify each state by rendering it headless Done: the Notepads screen (list, entries, wipe with confirmation).

## 6. Erasing, the safe area and chess

- [x] 6.1 Make what comes off a forced choice: an `erase` list on plan and answer whose entries are {id, because}, the id an enum of every listing id (para, line, mark, picture up to the listing's caps), the same for every job; an erase step only for what is pointed at; verify with unit tests that only listing ids are accepted, the schema declares only required keys in writing order, and line ids resolve to their marks (tests/test_erase_ids.py)
- [ ] 6.2 With the maintainer's go-ahead, check against the real server, as the pipeline's schema-order check did, that the erase entries arrive with their keys and values intact (tools/check_schema_order.py), and re-run the erase cases that failed on the tablet
- [x] 6.3 Take every kind of content's top from the one safe-area definition, clear of the toolbar across the top (placement, game pages, document pages); verify with unit tests
- [x] 6.4 Chess: play the moves the request already makes before the opponent replies, a board as wide as the safe area allows with its coordinates inside it, the portrait at the board's left edge and its name large and bold; verify with unit tests (tests/test_chess_and_safe_area.py)
- [ ] 6.5 With the maintainer's go-ahead, check the chess page, the coordinates and the portrait's name on the tablet

## 7. Real-run evidence

- [ ] 7.1 With the maintainer's go-ahead, run the maintainer's the pipeline dogfood cases through PaperDaemon's host on the maintainer's models and a dogfood notebook, record pass counts and times beside the pipeline's, and check the notepad screen against the notebook's notepad file
- [ ] 7.2 Run the same cases with a text-only model and with the image slot empty, and record which cases still pass
