# jobs/cleanup Specification

## Purpose
Finishes a job by erasing the instruction the job carried out, so the user is not left to clean up,
while keeping every word of the user's that was not that instruction.

## Requirements

### Requirement: The carried-out request is erased
After a job carries out a request, the request SHALL come off the page, typed or handwritten, when the
model ruled it a request that comes off and every step that answers it succeeded.

#### Scenario: A chart request
- **WHEN** a page says "chart my reading minutes this week", the model rules it a request that comes off,
  its chart step answers it, and the chart lands
- **THEN** the request is erased and the chart stays

### Requirement: Questions, notes and other requests stay
The host SHALL NOT erase an item the model ruled a question, conversation, a note or other, nor any item
the model did not rule to come off. A ruling that would erase a question, conversation or a note SHALL be
refused as inconsistent and returned to the model.

#### Scenario: A question
- **WHEN** a job answers "how far away is the moon?" and the model rules it a question that stays
- **THEN** the question stays on the page above its answer

#### Scenario: A to-do beside a request
- **WHEN** a page holds "call the plumber on Friday" and a chart request, the model rules the first a
  note that stays and the second a request that comes off, and the chart lands
- **THEN** the chart request is erased and the to-do line stays

### Requirement: When unsure, keep
An item the model did not rule to come off SHALL stay on the page.

#### Scenario: An ambiguous line
- **WHEN** the model rules a line as other, to keep
- **THEN** the line stays

### Requirement: What comes off is named by its id, a forced choice
The model SHALL name each item it rules on by the id the page's listing gave it -- a typed paragraph
`para:N`, a line of the user's handwriting `line:N`, an ink mark `mark:N`, a picture `picture:N` -- with
what the item is and whether it comes off. The tools' schema SHALL make the id a choice from a fixed list
of every id the listing can print, so a description cannot be written in its place. The list SHALL be the
same for every job, so the prompt the server has cached stays valid, and the listing SHALL never print an
id outside it. The host SHALL check that a chosen id exists on the page; a ruling on an id the page does
not have SHALL be refused and returned to the model, and nothing SHALL be erased by it. What the model
points at in words (an arrow, "this") is erased by pointing, not by an id.

#### Scenario: A typed request
- **WHEN** a page holds the typed request "Draw a lighthouse at dusk." as its first paragraph and the
  model plans the picture
- **THEN** the model rules `para:1` a request that comes off, its picture step answers `para:1`, and the
  request comes off once the picture lands

#### Scenario: An id the page does not have
- **WHEN** the model rules on `para:3` on a page with one typed paragraph
- **THEN** the ruling is refused and returned to the model, nothing is erased by it, and the job's record
  says why
