# models/lineups Specification

## Purpose
What a lineup is: a named set of models (a text model, and optionally an image model) with their harnesses, start scripts and tags. Every lineup is live; a job runs on the lineup whose tag is on its page.

## Requirements

### Requirement: Every lineup is live
PaperDaemon SHALL have no active lineup. Every lineup's tags SHALL be watched at once, and a job SHALL run on
the lineup that owns the tag that applies to its page: a page's tag over its notebook's, a notebook's over its
folder's. The host SHALL name the job's lineup to the engine before the job's first model call, and the
job's model calls and pictures SHALL go to that lineup's slots.

#### Scenario: Two lineups
- **WHEN** lineup A owns the tag "Ask", lineup B owns "Draw", one notebook is tagged "Ask" and one page of it
  is tagged "Draw"
- **THEN** that page is worked by lineup B and the notebook's other pages by lineup A, with no restart of the
  daemon or the host

### Requirement: A start script runs only when a different one is needed
The engine SHALL remember, per slot, which start script it last loaded (its file, or its inline text, with
its location). Before a call it SHALL run the job's lineup's script only when that script is not the one
running; it SHALL first end the server the other script started. A slot without a start script SHALL start
nothing and end nothing.

#### Scenario: Same script
- **WHEN** two lineups use the same start script and location, and jobs alternate between them
- **THEN** the script runs once

#### Scenario: Different script
- **WHEN** the next job's lineup has another start script for the text slot
- **THEN** the running text server PaperDaemon started is ended, and the other script runs

### Requirement: Lineup screen actions
The Lineup screen SHALL have Delete with Rename to its right, and no way to activate a lineup. Its tabs SHALL
be Text / Reasoning, Image, Network, Tagging, Memories, Jobs and Tests; the setup screens SHALL have only the
first four. Tests and model checks SHALL act on the lineup on screen.

#### Scenario: Jobs per lineup
- **WHEN** the user opens a lineup's Jobs tab
- **THEN** only the jobs that lineup worked are listed (a job not yet worked, by its tag)
