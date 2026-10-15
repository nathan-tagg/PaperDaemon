# Proposal

## Why

The daemon is what makes the tablet feel alive: tag a page and it gets answered. The pipeline's daemon
learned, over many real pages, which pages need work and which must be left alone: a page edited
again comes back, a page retagged gets another look, pages that were already old when a notebook was
tagged stay untouched, and PaperDaemon's own writes never wake it. PaperDaemon needs that daemon, with those
rules, inside the engine.

## What Changes

- One daemon per reMarkable account, running inside the engine, woken by the cloud's change
  notifications.
- A page needs work when it carries the trigger tag, or when its notebook or any folder above it does.
- The tag "ignore" on a page, a notebook or a folder keeps every job away from it; "ignore" and "sprompt"
  are fixed tag names, not settings.
- A ledger records each page's state and a fingerprint of its content, and decides: new, waiting,
  baseline, reopened, retagged, done or skipped.
- Jobs start only after a page stops changing, one at a time.
- A notebook's system prompt page is never a job, and anything in the trash is gone.
- The overview shows what the daemon saw and what each job did, and the user can pause the daemon.

## Capabilities

### New Capabilities
- `jobs/dispatch`: which pages become jobs and when, the ledger and its states, tags and inheritance,
  pausing, and what the overview shows.

### Modified Capabilities
None.

## Non-goals

- What a job does once dispatched (add-job-host).
- A back-and-forth "keep watching this page" mode.
- More than one reMarkable account per engine.

## Impact

- New package `paperdaemon/daemon/`: the scan, the ledger and the dispatch loop, ported from the pipeline's
  `rm_scan` and `rm_daemon`.
- A ledger file in the data folder.
- New API routes for the overview's job list and for pausing and resuming.
