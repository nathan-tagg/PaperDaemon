# Proposal

## Why

A lineup was "active" or not, and one trigger tag decided whether a page was a job at all. The maintainer's
ruling: there is no active lineup. Every lineup is live, and the tag the user puts on a page, notebook or folder
says which lineup works it. A local model's start script runs only when the job needs a different one from the
last loaded. Each tag carries its own prompt. Lineups also need a place for what their model learns about
working for the user.

## What Changes

- No active lineup: "Set as active lineup" is gone, and every lineup's tags are watched at once.
- A job runs on the lineup that owns its tag (folder < notebook < page, the most specific wins). The engine
  remembers the start script last loaded per slot and runs another only when the job's lineup needs a different
  one; a slot reached by an API key needs none.
- The Tagging tab is an ordered list of tag cards (a 3x3 dot drag handle, a tag field, a prompt field). A page's
  prompt is the prompts of its lineup's tags on its page, notebook and folders, in the tab's order, with the
  notebook's standing instructions page (sprompt) always last.
- Tags are unique across PaperDaemon, including the ignore and sprompt tags, which move to Settings.
- The decompose inbox is never worked, whatever it is tagged with; it gets no ignore tag.
- Each lineup has memories: lessons its model learned about working for the user. The model adds, replaces and
  removes them (at most 30); the user edits and deletes them on the lineup's Memories tab.
- Jobs move from their own screen into a tab of the lineup, listing that lineup's jobs.
- Rename sits to the right of Delete.

## Capabilities

### New Capabilities
- `models/memories`: what a lineup remembers, who changes it, and where it is shown.
- `models/lineups`: every lineup live, chosen per job by tag; start scripts by need.
- `jobs/tagging`: tags with prompts, their order, uniqueness, the shared ignore and sprompt tags, the inbox.

## Non-goals

- The user adding memories (not yet).
- Two local servers for one slot at once: one start script per slot is loaded at a time.

## Impact

- `settings.py` (tag lists, global ignore/sprompt, in-use lineup), `ledger.py` (many triggers, the inbox),
  `loop.py` and `models/lineup.py` (every lineup in the run file), `card.py` and `models/hotswap.py` (script
  identity), `server.py` (`/host/lineup`, memories routes, lineup-scoped model routes), the host (per-job
  lineup, prompt order, memories), new `memories.py`, and the Lineup, Setup, Settings and Jobs screens.
