# jobs/notebook-prompt Specification

## Purpose
Lets the user give a notebook standing instructions on a page of its own, which the host follows on
every job in that notebook, word for word.

## Requirements

### Requirement: A page tagged sprompt holds the notebook's instructions
A page tagged `sprompt` SHALL hold its notebook's standing instructions, read from its typed text and
its handwriting, and they SHALL apply to every job in the notebook, whatever other tags the notebook and
its pages carry. The page itself SHALL never be a job. The tag counts only on a page; on a notebook or a
folder it means nothing. Its name is fixed and universal, matched ignoring case.

#### Scenario: A coloring-book notebook
- **WHEN** a notebook's first page is tagged `sprompt` and says to turn each idea into a coloring page
- **THEN** every job in that notebook receives those instructions, and the first page is never answered

### Requirement: The instructions are used as written
The host SHALL give the model the notebook's instructions exactly as the user wrote them, without
rewording, summarizing or merging them into other text.

#### Scenario: Rough spelling
- **WHEN** the instructions hold a misspelled word
- **THEN** the model receives the misspelled word as written

### Requirement: The instructions come last in the system instructions
The host SHALL place the notebook's instructions after the base brief and the harness's additions, as
the last part of the system instructions, and SHALL tell the model at the decision point that this
notebook has instructions of its own to apply first.

#### Scenario: Instructions that forbid revisiting pages
- **WHEN** the instructions say never to add work to a finished page and the user writes on one
- **THEN** the model is told to apply the notebook's instructions first, and may skip the page citing them

### Requirement: Long instructions are cut at 10,000 characters
The host SHALL give the model at most the first 10,000 characters of the instructions, and SHALL record
in the job's record that they were cut.

#### Scenario: Very long instructions
- **WHEN** the instructions run to 12,000 characters
- **THEN** the model receives the first 10,000, and the job record says the instructions were cut
