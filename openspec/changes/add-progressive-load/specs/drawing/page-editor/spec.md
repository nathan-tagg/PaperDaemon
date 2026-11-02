## ADDED Requirements

### Requirement: A page's strokes come in a frame at a time
When a page opens on the graphics card, the editor SHALL show its paper, template, typed text, pictures and the PDF's or
book's page under it as soon as the engine has said what the page is without its strokes -- an answer the engine makes
without reading a stroke -- then put its strokes on the page in the page's order, as many as one frame holds each frame,
each frame's drawn over the ones before; when the last are in, the page SHALL be what drawing it whole shows, pixel for
pixel. Nothing SHALL cover the page while it comes in: keys, presses and the wheel SHALL wait, unseen, until the strokes
are in. The editor SHALL NOT show a picture of the page in its place.

#### Scenario: A page the engine has not read yet
- **WHEN** the user opens a page of 150,000 strokes the engine has not read since it started
- **THEN** its paper, template and text show while the engine is still reading its strokes, and no spinner shows

#### Scenario: A heavy page opened
- **WHEN** the user opens a page of 150,000 strokes on an integrated card
- **THEN** the page shows within a few frames and its strokes appear over the frames after, none stalling the page

#### Scenario: Undo pressed while it comes in
- **WHEN** the user presses Ctrl+Z before the page's strokes are all in
- **THEN** the undo waits until they are in, then runs

### Requirement: A page opens without waiting on the one before it
New page SHALL show the new page at once, whatever the size of the page it follows. A page opened again after it was
drawn on SHALL come from the form the engine made of it as it was saved, never without what was drawn last. Opening a
page SHALL NOT compile again the editor's shaders the window has compiled already, whatever was done on the page before.

#### Scenario: New page after a heavy page
- **WHEN** the user draws on a page of 150,000 strokes and presses New page
- **THEN** the blank page shows within half a second

#### Scenario: A notebook opened again after drawing
- **WHEN** the user draws on a page, closes the notebook and opens it again a few seconds later
- **THEN** the page is read in a tenth of a second, with the strokes just drawn
