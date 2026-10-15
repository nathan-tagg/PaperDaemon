# Tasks

## 1. Scan and ledger

- [ ] 1.1 Port the content fingerprint from the pipeline and pin its value on fixture pages with a unit test Ported (`ledger.page_state`: strokes and typed text, not the file's bytes); a pinned fixture value is still to write.
- [x] 1.2 Port tag inheritance and the ignore tag, and verify with a fixture library of folders, notebooks and pages Done: `tests/test_fixed_tags.py` (inheritance from folders and notebooks, ignore at every level, every lineup's tags watched at once, the inbox never a job).
  - The fixed names "ignore" (any level) and "sprompt" (a page only, never a job) are checked by
    tests/test_fixed_tags.py on a fixture mirror.
- [x] 1.3 Port the states (new, waiting, baseline, reopened, retagged, done, skipped) and verify each with a fixture test, including a retag read from tag timestamps Done: `tests/test_ledger_states.py` (new, waiting, baseline, done, reopened, retagged, cleared, a dead worker's claim).
- [x] 1.4 Skip system prompt pages and trashed items, and verify with fixture tests Done: `tests/test_fixed_tags.py` (an sprompt page is never a job), `tests/test_sync.py` (the trash is gone).

## 2. Dispatch

- [ ] 2.1 Run the daemon as an engine thread behind a data-folder lock, and verify a second start on the same folder runs no daemon Superseded by the design the engine runs: the daemon and the host are two child processes of the engine (`loop.py`), started and supervised by it; one engine per data folder.
- [ ] 2.2 Pull on other devices' change notifications, check the root at a low rate while notifications are down, and verify with a stubbed notifier
- [ ] 2.3 Settle, then dispatch one job at a time in ready order; record the fingerprint after the job's last push; verify with a stubbed host that a job's own write does not reopen the page
- [x] 2.4 Add pause and resume, and verify pages tagged while paused are dispatched after resuming Done as Pause and Resume on the Overview (`/api/v1/loop/stop|start`): pages tagged while paused are queued by the next scan.

## 3. API and overview

- [ ] 3.1 Add the job list and pause routes under `/api/v1/daemon`, and verify them with API tests Superseded: `/api/v1/loop` and `/api/v1/jobs` (jobs by lineup).
- [ ] 3.2 Show the jobs on the overview screen, and verify by rendering it headless with fixture jobs Superseded by the maintainer: each lineup's jobs are its Jobs tab.

## 4. Real-run evidence

- [ ] 4.1 With PaperDaemon's own device token and the maintainer's go-ahead: tag a page on the tablet, write a follow-up, retag an unchanged page, tag a notebook with old pages, mute a page; record which pages were dispatched and in what state
