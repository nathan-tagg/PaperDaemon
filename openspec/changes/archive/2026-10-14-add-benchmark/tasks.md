# Tasks

## 1. Benchmark library and cases

- [ ] 1.1 Build the first benchmark library in mirror format under `tests/benchmark/`, with typed and handwritten cases for the daemon (dispatch, the ignore tag, a retag, the system prompt page, a fresh ledger's baseline), reading, answers, charts, pictures, coloring pages, mark-ups, erasing, documents, the notebook prompt, the notepad, tags, search and fetch; verify it loads as a mirror Built in part: five page cases in `tests/benchmark/cases` (typed and handwritten questions, a chart, a drawing, a coloring page); the daemon's cases (dispatch, ignore, retag, sprompt, baseline) are unit tests instead (`tests/test_ledger_states.py`, `tests/test_fixed_tags.py`).
- [x] 1.2 Write the case format (page states in order, picture seeds, the expected outcome) and the checks that read the records and the page; verify each check with a hand-made passing and failing result Done: each case's request and expected outcome; `tests/test_benchmark_and_studio.py` (the fixtures, judging).

## 2. Running

- [x] 2.1 Open a scratch mirror from the library, start a daemon on it with its own ledger, deliver each case's page states as a sync would, and push to a local stand-in; verify with a stubbed cloud that nothing leaves the machine and that the scratch mirror is gone after the run Done: a run starts from a fresh copy of the fixtures in its own state folder and mirror, documents staged and never published (`RM_HOST_DRY_DOCS`), the tag watched being the cases' (`tests/test_engine.py`, `tests/test_benchmark_and_studio.py`).
- [x] 2.2 Hold the user's new jobs during a run and dispatch them after, and begin a run asked for mid-job when that job ends; verify with fixture libraries that a page tagged mid-run is dispatched after the run Done as built: a run waits until the tablet loop is idle, pauses it, and puts it back as it was; pages tagged meanwhile are queued by the next scan.
- [ ] 2.3 Run each slot's model test first, and report a case the configuration cannot serve as not available with the reason; verify with an empty image slot and no search provider Built as the report card: a case a lineup cannot serve shows as off with its reason (no image model); search, social, weather and maps are tested directly (`tests/test_report_card.py`).
- [x] 2.4 Stop a run on request, then delete the scratch mirror and release the user's held jobs; verify with a unit test Done: Cancel ends the run, and its state folder is left for the record (`benchmark.cancel`).

## 3. Report

- [x] 3.1 Build the report from the records: the configuration, results by capability, each case's page, result and reason, and the time in each stage including hot swaps and model speed; fill it in as cases finish; keep only the latest; verify by rendering the screen headless Done as the Tests tab's report card and the case table with a comparison between two lineups' runs.

## 4. Real-run evidence

- [ ] 4.1 With the maintainer's go-ahead and the maintainer's card free, run the benchmark on the maintainer's models with hot swapping, on a text-only model, and with the image slot empty, and record the three summaries here
