# Proposal

## Why

The host is where the pipeline's hardest lessons live. Letting the model steer the mechanics (where things
go, what to erase, when to commit) made jobs slower and wrong more often; making the host drive, with
the model making one decision about what the page needs, took the maintainer's benchmark jobs from 621 s to
177 s and nine out of nine. Around that core grew the notebook's own system prompt, a per-notebook
notepad for conversation memory, a sweep that erases only the request a job carried out, and tagging
behind explicit direction only. PaperDaemon v1 has to do all of it exactly as the pipeline does, with whatever
models the user configured.

## What Changes

- The host runs each dispatched job by the text harness's protocols. It reads the page, and then:
  - the intake protocol says what the model is shown and told
  - the output protocol says what the model hands back
  - each task's protocol says what the host does for it
  - validate() says what is refused before the host commits to the page and the cloud
- Where a harness leaves placement to the host, the model says what goes on the page and roughly how
  big, and the host decides where, so nothing overlaps.
- Tasks are offered by capability: no image slot, no picture tasks; a model that cannot see gets the
  page as text.
- A notebook's system prompt page is used word for word, as the last part of the system instructions.
- Each notebook has a notepad the host reads and writes, filed by page, emptied by `/wipe`, and shown
  in the app.
- After a job, the host erases the request it carried out and nothing else of the user's.
- The model may tag the current page only when the user named that tag.
- Runaway output is stopped by token limits and repetition checks, never by a clock.

## Capabilities

### New Capabilities
- `jobs/host`: running a job by the harness's protocols, layout, tasks by capability, validate()
  before commit, skipping, runaway limits, and where new documents may go.
- `jobs/notebook-prompt`: the notebook's standing instructions page and how the host uses it.
- `jobs/notepad`: the per-notebook notepad, the `/wipe` command, and the notepad screen.
- `jobs/cleanup`: erasing the carried-out request, and what always stays.
- `jobs/tags`: the tag step and the explicit-direction check.
- `jobs/games`: games played on a page, starting with chess: the moves a request already makes, and the
  chess page's layout.

### Modified Capabilities
None.

## Non-goals

- The drawing tools themselves (add-drawing-tools) and web search (add-web-search).
- The daemon's choice of pages (add-tablet-daemon).
- A shipped harness whose model does the whole job itself. The protocols allow one; none ships in v1.

## Impact

- New package `paperdaemon/host/`, ported from the pipeline's `rm_host`, `rm_plan`, `rm_steps` and related
  modules, split by responsibility and cleaned for publishing.
- The base brief ships as a text file. The base harness's intake builds on it; a harness adds lines
  through `brief_additions()` or writes its own intake.
- Notepads live in the data folder, one file per notebook.
