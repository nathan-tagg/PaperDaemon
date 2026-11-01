## ADDED Requirements

### Requirement: A dragged selection is drawn in layers
While a selection is held, the editor SHALL draw the rest of the page once, split by the page's order: the strokes
before the selection as a picture, the strokes after it as what they do to what lies under them. Each frame of a drag
SHALL draw only the selection and the strokes among it in the page's order, over the first and under the second, and
SHALL show what drawing the whole page shows, pixel for pixel; a frame that cannot be made so SHALL be drawn whole.

#### Scenario: A highlighter dragged across a pen written after it
- **WHEN** the user drags a highlighter stroke across a blue pen stroke written after the highlighter
- **THEN** every frame shows the pen blue over the highlighter, as the whole page drawn with the highlighter there

#### Scenario: A heavy page on an integrated card
- **WHEN** the user drags a selection on a page of 150,000 strokes on a machine with only an integrated card
- **THEN** each frame draws the selection and the strokes among it, not the rest of the page

### Requirement: Letting go of a selection keeps the page answering
When a selection moved on the graphics card is let go, the editor SHALL make the strokes it lands as from the records the
card holds, a little at a time, the page answering meanwhile; what would change the page (a key, a press) SHALL wait
until it has landed and then run. Its undo and redo SHALL move the same strokes back and forth on the card, made ready
the same way. The page after each SHALL be what drawing it whole shows, and what the page shows opened again, pixel for
pixel.

#### Scenario: A whole decomposition moved on an integrated card
- **WHEN** the user moves 86,000 strokes of a 150,000-stroke page and lets go, on an integrated card
- **THEN** the page never stops answering for more than 50 ms, and shows the strokes where they were let go

#### Scenario: Undo pressed while it lands
- **WHEN** the user presses Ctrl+Z before a large selection has landed
- **THEN** the undo waits for it to land, then puts every stroke back where it was, pixel for pixel
