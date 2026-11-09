## ADDED Requirements

### Requirement: Another page of the notebook can be read
While it rules and plans, the model SHALL be able to read any other page of the same notebook in words: its typed
text, exact, and its handwriting as the reader reads it, line by line. A request that points at another page ("my
budget on page 1") SHALL be answered from that page, never by asking the user to write it again. Pages are counted as
the tablet counts them; the page the job is on is not read this way, since the model has it already.

#### Scenario: A total from the page before
- **WHEN** page 1 holds a typed budget and the request on page 2 asks for its total
- **THEN** the model reads page 1, and the total is written on page 2

#### Scenario: A page with nothing in words
- **WHEN** the page named holds only a drawing
- **THEN** the reading says so, and the model rules with that
