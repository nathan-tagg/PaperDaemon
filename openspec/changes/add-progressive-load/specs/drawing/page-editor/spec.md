## ADDED Requirements

### Requirement: A page's strokes come in a frame at a time
When a page opens on the graphics card, the editor SHALL show its paper, template and text at once, then put its
strokes on the page in the page's order, as many as one frame holds each frame, each frame's drawn over the ones
before; when the last are in, the page SHALL be what drawing it whole shows, pixel for pixel. Keys, presses and the
wheel SHALL wait until the strokes are in. The editor SHALL NOT show a picture of the page in its place.

#### Scenario: A heavy page opened
- **WHEN** the user opens a page of 150,000 strokes on an integrated card
- **THEN** the page shows within a few frames and its strokes appear over the frames after, none stalling the page

#### Scenario: Undo pressed while it comes in
- **WHEN** the user presses Ctrl+Z before the page's strokes are all in
- **THEN** the undo waits until they are in, then runs
