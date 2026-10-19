# Spec Delta

## ADDED Requirements

### Requirement: Page units are fixed
PaperDaemon SHALL treat a page's coordinates as fixed units, the same on every frame: stroke widths, text
sizes, line spacing and typed-text columns SHALL NOT scale with the page's frame.

#### Scenario: The same stroke on two frames
- **WHEN** a stroke 24 units wide is drawn on a 1404 x 1872 page and on a 1620 x 2160 page
- **THEN** both renders draw it 24 units wide, at the same size relative to the page's units

### Requirement: Only the drawable square is shown
PaperDaemon SHALL show a page's ink and typed text only inside its drawable square: as wide as the page
is tall, centered on the page's center line, from y 0 down. Content outside the square SHALL be kept in
the page and SHALL NOT be shown. A page SHALL extend downward past its frame height to hold content
below it.

#### Scenario: A stroke that leaves the square
- **WHEN** a stroke starts inside the drawable square and runs out past its edge
- **THEN** the part inside is drawn, the part outside is not, and every point stays in the page

#### Scenario: Text on a tiny frame
- **WHEN** a 200 x 266 page holds a paragraph in the wide column
- **THEN** its lines are laid out 1152 units wide and cut at the edges of the 266-wide square

### Requirement: Typed text uses the tablet's three columns
A page's typed text SHALL be one block in one column, centered on the page's center line and starting
at y 234, in one of three widths whatever the frame: wide (x -576, width 1152), medium (x -468, width
936) or narrow (x -370, width 740). PaperDaemon SHALL lay out a stored column at its stored width.

#### Scenario: Medium text on a Paper Pro page
- **WHEN** the user sets a 1620 x 2160 page's text to medium
- **THEN** the page stores x -468 and width 936, and its lines wrap within that width

#### Scenario: A stored width PaperDaemon has not seen
- **WHEN** a page stores a column 800 wide
- **THEN** its text is laid out 800 wide, at the stored x

### Requirement: Lists are body text
Bullets, numbers and checkboxes SHALL be body-text paragraph styles: a list paragraph SHALL NOT also be a
title, header or section. A checked checkbox SHALL be drawn as a filled box with a white tick, with
every line of its paragraph struck through.

#### Scenario: A checked item that wraps
- **WHEN** a checked checkbox paragraph runs to two lines
- **THEN** the box is filled with a white tick and both lines are struck through
