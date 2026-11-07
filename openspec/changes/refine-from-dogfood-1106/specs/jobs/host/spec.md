## ADDED Requirements

### Requirement: A chart's data is not a loop
The host SHALL take a model's output for a loop only when one chunk repeats back to back at least six times and
over at least 400 characters. A short value repeated in a chart's data (a constant series, an average line typed as
equal numbers) SHALL NOT stop the turn.

#### Scenario: A year of weeks at one value
- **WHEN** a chart step's series holds the same number 52 times
- **THEN** the turn is not stopped, and the chart is drawn

#### Scenario: A real loop
- **WHEN** a tool call's arguments repeat "0, " two hundred times
- **THEN** the host stops the turn as a loop

### Requirement: Additions onto one drawing share it
Places the model puts ON a mark on the page (`side: "on"`) SHALL NOT be refused for overlapping each other: each
is the drawing it goes on, not new room. Every other place SHALL still keep clear of everything.

#### Scenario: A hat, a scarf and buttons for the snowman
- **WHEN** a plan has three draw steps, each near the snowman's mark with side "on"
- **THEN** the plan is accepted, and each addition is drawn on the snowman

### Requirement: A picture placed over an old one replaces it
A picture that lands over most (40%) of a picture already on the page SHALL take that picture's place: the old one
comes off when the new one lands. This SHALL hold for charts, coloring pages and pasted pictures alike.

#### Scenario: A coloring page made again
- **WHEN** the user asks for a coloring page to be redone, and the new one lands where the old one was
- **THEN** the page holds only the new coloring page

### Requirement: An addition to a drawing is drawn on its parts and stays where it is drawn
A step that draws on a drawing already on the page SHALL be told the drawing's parts (the boxes of its biggest
strokes, top to bottom) and SHALL draw in the page's own numbers. What it draws near the drawing (within the
drawing's own size of it) SHALL stay exactly where it was drawn, never scaled, moved only as far as needed to stay on
the page. Only a figure far from the drawing, made on a grid of its own, SHALL be fitted into the drawing's box.

#### Scenario: A top hat for the snowman
- **WHEN** the model draws a hat above the snowman's head, outside the snowman's own box
- **THEN** the hat stays on the head, at the size it was drawn

### Requirement: A plan hears all its problems at once
A plan refused for its fields or rulings SHALL also be told what its steps would be refused for, in the same reply,
so it can be fixed in one turn. A circle, highlight, underline or strike that names neither the id it is in, nor the
words, nor where it is SHALL be refused before anything runs.

#### Scenario: A circle described only in words
- **WHEN** a plan's circle step says "circle the word 'Vienna' in the first answer paragraph" with no target or words
- **THEN** the plan is refused with what the step needs, and nothing has run

### Requirement: A reply goes under what it answers
A written reply SHALL start right under the lowest item it answers that stays on the page (a typed paragraph, a
handwritten line) when the free paper there, down to the next thing on the page, holds the whole reply; otherwise it
SHALL go below everything, as before. A chart a plan gave its spec SHALL be drawn from that spec without a turn of
its own.

#### Scenario: A question at the top, a note at the foot
- **WHEN** a typed question sits at the top of a page, a note to someone sits near its foot, and the answer fits in
  the paper between them
- **THEN** the answer is written right under the question, and the note stays below it, untouched
