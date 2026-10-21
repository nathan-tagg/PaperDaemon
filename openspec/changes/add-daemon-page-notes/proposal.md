# Proposal: add-daemon-page-notes

## Why

A job that fails leaves the user guessing: nothing on the tablet says the daemon got the page, what the host
made of it, or why it stopped. And a job that failed once was left alone, even when trying it again would
have worked. The maintainer asked for both: the daemon writes on the page as he works, and a failed job is
tried again a set number of times.

The first version (0.1.52) put each note on a layer of its own and sent it up as a copy of the page. The
tablet merges the copies it receives, and notes made from different copies with the same ids piled up on
top of each other. Their strokes were then read as the user's handwriting.

## What Changes

- New capability `jobs/page-notes`: the daemon's notes on the page (Settings: Notes on the page) and his
  retries (Settings: Retries). What the notes say and when, where they go, the layer they are on and its
  name (Settings: Daemon layer), the daemon's own author id, erasing before every write, the retry box, and
  how the renderer and the fingerprint leave the notes out.
- The host reports what it does as it works: what it read on the page, its plan, and each step as it ends.
- Handwriting is read where the render puts it: the page's picture is the whole page and whatever lies
  past its frame, from a page point at its top-left, not the frame scaled.

## Impact

- `paperdaemon/pipeline/daemon/notes.py`, `paperdaemon/pipeline/daemon/__init__.py`
- `paperdaemon/pipeline/page/render.py`, `paperdaemon/ledger.py`, `paperdaemon/remarkable/fastrm.py`
- `paperdaemon/pipeline/host/steps.py`, `paperdaemon/pipeline/host/__init__.py`, `paperdaemon/pipeline/host/intake.py`
- `paperdaemon/settings.py`, `paperdaemon/ui/settings.js`, the strings in every language
