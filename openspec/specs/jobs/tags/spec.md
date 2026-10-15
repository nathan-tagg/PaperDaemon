# jobs/tags Specification

## Purpose
Lets a job tag the page it worked on, only when the user explicitly asked for that tag, so that a
notebook can, for example, have each finished page muted for good.

## Requirements

### Requirement: Tags only by explicit direction
The model SHALL be able to ask for a tag on the job's own page only, quoting the user's words that ask
for it. The host SHALL apply the tag only if the quote is found (whitespace and case aside) in the
notebook's system prompt, the page's typed text, or the reader's reading of the page's handwriting, and
names the tag as a whole word; otherwise the step SHALL fail with "no tag named X was asked for".

#### Scenario: Asked for in the notebook's instructions
- **WHEN** the notebook's instructions say "tag every finished page ignore", a job finishes a page, and
  the model quotes those words
- **THEN** the page is tagged "ignore"

#### Scenario: Not asked for
- **WHEN** the model asks to tag a page "done", and its quote appears nowhere in the instructions or on
  the page
- **THEN** the step fails with "no tag named done was asked for", and the page gets no tag

### Requirement: A tag lands only on a job that succeeded
The host SHALL apply a tag when the job commits, and only if no step and no erasure failed.

#### Scenario: A picture that failed
- **WHEN** the instructions call for the tag "ignore" but the job's picture failed to generate
- **THEN** the page is not tagged, so the request stays visible to the daemon

### Requirement: The ignore tag keeps the daemon away for good
A page the host tags "ignore" SHALL never be dispatched again while it carries that tag.

#### Scenario: A finished coloring page
- **WHEN** a job tags a finished page "ignore" and the user later writes on it
- **THEN** no job starts for that page

### Requirement: Jobs never remove or spread tags
A job SHALL NOT remove a tag, and SHALL NOT tag any page, notebook or folder other than the job's own
page.

#### Scenario: Asked to tag the whole notebook
- **WHEN** the model asks to tag the notebook instead of the page
- **THEN** the host refuses the step
