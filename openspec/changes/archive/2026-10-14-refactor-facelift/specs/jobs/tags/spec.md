# Spec Delta

## MODIFIED Requirements

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
