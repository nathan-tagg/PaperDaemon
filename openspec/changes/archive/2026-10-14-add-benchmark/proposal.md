# Proposal

## Why

A PaperDaemon user can plug in any model. Whether a configuration can run the pipeline (notice a page,
read it, plan an answer, draw a chart, make a coloring page, swap servers) is not knowable from the
models' names. The benchmark is a major feature: it opens its own
mirror, performs daemon, host, harness, model and image model operations across consistent
benchmarks, and gives back a comprehensive idea of what the configuration is capable of.

## What Changes

- **One button, the whole pipeline.** A fixed set of cases runs through the daemon, the host, the
  harnesses, the text model, the image model and hot swapping. It runs on a mirror of its own, never
  the user's library, and writes nothing to the cloud.
- **The benchmark plays the tablet.** It delivers each case's pages into its mirror the way a sync
  does, so its own daemon notices and dispatches them.
- **The same run every time.** Every run uses the same cases, order and picture seeds, so two
  configurations can be compared.
- **A report on the configuration:**
  - what it can and cannot do, by capability
  - each case's page and what went wrong
  - where the time went: dispatch, reading, model turns, pictures, decomposing, hot swaps, the commit

## Capabilities

### New Capabilities
- `testing/benchmark`: the benchmark library and cases, running them through the whole pipeline, and
  the report.

### Modified Capabilities
None.

## Non-goals

- Ranking models publicly.
- Tuning the brief or the harnesses automatically from results.
- Running on the user's own pages. That is a real run.

## Impact

- New package `paperdaemon/benchmark/` and a bundled benchmark library under `tests/benchmark/`.
- A benchmark screen in the UI and routes under `/api/v1/benchmark`.
