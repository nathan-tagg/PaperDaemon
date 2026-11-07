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
