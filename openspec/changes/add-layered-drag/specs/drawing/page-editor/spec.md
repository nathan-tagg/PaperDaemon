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
