# jobs/tagging Specification

## Purpose
How a page's tags pick the lineup that works it and the prompts that job is given: every tag belongs to one lineup, carries its own prompt, and the most specific tag on a page's path (page, notebook, folder) decides.

## Requirements

### Requirement: Tags with prompts, in order
A lineup's tags SHALL be an ordered list, each a full tag the lineup watches for with its own prompt (blank
allowed). A page's prompt SHALL be the prompts of its lineup's tags found on the page, its notebook and the
folders above it, in the Tagging tab's order; the text of the notebook's standing instructions page SHALL
always come last, for the whole notebook. The Tagging tab SHALL say so, SHALL recommend one tag with a blank
prompt, and SHALL let the user reorder the cards by a 3x3 dot handle on each card's left edge (or its arrow
keys).

#### Scenario: Order
- **WHEN** a page carries "Plain" and "Draw" of one lineup, listed Plain then Draw, in a notebook with an sprompt
  page
- **THEN** the job's system prompt holds Plain's prompt, then Draw's, then the sprompt page's text

### Requirement: Tags are unique
No tag SHALL belong to two lineups, and none SHALL be the ignore or the standing instructions tag, matched
without regard to case. The ignore and standing instructions tags SHALL be set in Settings, for every lineup.

#### Scenario: Taken
- **WHEN** the user saves a lineup with a tag another lineup owns
- **THEN** the save is refused with the reason

### Requirement: The inbox is never a job
The decompose inbox notebook SHALL never be worked, whatever it is tagged with, and SHALL get no ignore tag.

#### Scenario: Tagged inbox
- **WHEN** the inbox notebook carries a watched tag
- **THEN** no page of it is queued
