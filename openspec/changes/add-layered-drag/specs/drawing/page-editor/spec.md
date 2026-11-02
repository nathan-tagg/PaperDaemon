## ADDED Requirements

### Requirement: A dragged selection is held as a picture
When a selection is taken up on the graphics card, the editor SHALL draw it once as a picture and the page once without
it, and each frame of a drag SHALL put the picture where the frame takes it -- moved, turned or resized -- drawing no
stroke. While it moves, how it blends with the strokes under and over it MAY differ from the whole page drawn. Let go,
the page SHALL show what drawing it whole shows, pixel for pixel.

#### Scenario: A highlighter dragged across a pen written after it
- **WHEN** the user drags a highlighter stroke across a blue pen stroke written after the highlighter and lets go
- **THEN** the page shows the pen blue over the highlighter, as the whole page drawn with the highlighter there

#### Scenario: A heavy page on an integrated card
- **WHEN** the user drags a selection of any size on a page of 150,000 strokes on a machine with only an integrated card
- **THEN** each frame draws the picture alone, under a millisecond of the card's time, and keeps up with the pointer

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
