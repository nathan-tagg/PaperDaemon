# Proposal: add-layered-drag

## Why

Dragging a selection on a heavy page is slow and jumpy on an integrated card. Each frame draws the page again
wherever the selection was and is now, every stroke that reaches there, the selection's own and everyone else's.
Measured on the integrated card on a page of about 150,000 strokes: a small selection cost about 20 ms of the card's
work a frame, one of 39,751 strokes 61 ms (105 ms at the 90th percentile), and a large one froze the window. The
maintainer's ruling: all development time goes to the integrated card, exact every frame, never below 60 frames a
second.

## What Changes

- While a selection is held, the rest of the page is drawn once, split by the page's order: the strokes before the
  selection in the order are drawn into a picture of their own; the strokes after it are kept as what they do to
  whatever lies under them (their pens cover it; their highlighters darken it; their pencil grain and washes blend
  over it, drawn again where the selection is). Each frame draws only the selection and the strokes that lie between
  its strokes in the order, onto the first picture, and puts the later strokes over them.
- Every frame shows what drawing the whole page shows, pixel for pixel. A case that cannot be made so is drawn the
  way it is now.
- The pictures exist only while a selection is held and are freed when it is let go.

## Impact

- Affected specs: drawing/page-editor.
- Code: `ui/editor.html` (the card module's move, its draws by span of the page's order), `ui/shaders.js` if a pass
  needs a shader of its own.
- Graphics memory: three working-canvas textures while a selection is held.
