# Design: add-layered-drag

## Context

The editor's listed draws (`GL` in `ui/editor.html`, CULL and STROKES in `ui/shaders.js`) draw every stroke at the
depth of its place in the page's order (depth32float, compare less: a later stroke is nearer). Pens are drawn first,
depth tested and written, no blend: the latest pen over a pixel is what it shows. Then, level by level (a level is a
run of highlighters and the grain and wash strokes after it in the page's order), the level's highlighters with a
minimum blend, depth tested and not written, so they darken a pixel only where no later pen lies; then its grain and
wash strokes, depth tested and written, each blended over what is earlier once (alpha blend).

At a pixel, then, the page shows a fold in the page's order: the latest pen's color (or the paper), then each later
highlighter's minimum and each later grain or wash stroke's blend, in order. Strokes earlier than the latest pen never
touch the pixel. Every step is the same hardware operation on the same 8-bit values however the page is split, as
long as the steps run in the page's order.

A drag today (`moveTo`, `remarked`) moves the selection's records in place on the card, marks where they were and
where they are, and draws the whole page again inside the marks: the selection and every other stroke there.

## Measured (before any change)

The integrated card (AMD Radeon, Direct3D 12), the maintainer's heaviest page: 149,807 strokes (110,065
highlighters, 37,971 fineliners, 1,420 pencils, 351 markers). Each pass timed on the card (timestamp queries), the
median of 20 frames of a drag, ms a frame:

| selection (strokes) | marks (two passes) | move | cull | draw | frame |
|---|---|---|---|---|---|
| small (4,596) | 1.8 | 0.1 | 8.4 | 9.0 | 19.8 |
| medium (39,750) | 22.1 | 1.8 | 32.0 | 55.8 | 111.7 |
| large (114,969, drawn whole) | | 4.6 | 52.6 | 69.9 | 128.3 |

Where a lasso's strokes lie in the page's order on that page:

| selection | selected | not selected, between its first and last | runs |
|---|---|---|---|
| small | 2,322 | 144,963 | 1,421 |
| medium | 26,692 | 121,152 | 8,183 |
| large | 120,356 | 28,506 | 3,568 |

On a decomposed picture a lasso's strokes run through the whole of the page's order, so the split by order (D1)
leaves almost the whole page in the between span: it would draw what is drawn now. The page's pens could be drawn
once whatever their order (a pen covers, whatever was drawn before it), but there three strokes in four are
highlighters, whose darkening depends on which pen is latest under them. **The split by order is not built; the
choice of what replaces it is the maintainer's.**

## The drop and its undo (measured)

The same card and page, the maintainer's demo decomposition: its 86,254 highlighters selected, moved and let go, then
undone and done again. The longest the page's thread was busy at once (the browser's long tasks; none longer than 50 ms
afterwards), and the wait until it shows the result, in ms:

| | before: longest | after: longest | after: shown |
|---|---|---|---|
| let go | 832 | 35 | 430 |
| undo | 236-325 | 38 | 145 |
| redo | (not measured) | 30 | 92 |
| the save after the drop | (one message) | none over 50 | |

Before, the strokes the drop made were each made again point by point (2.9 million points), then compared with what the
card held, and the undo put every one of the old strokes up again. After: each part is made from the records the card
read back, as a fresh part of that stroke would be (a highlighter's turns aside: they are worked out where it is drawn),
and takes its stroke's place; the undo writes each stroke's records back in that place from its part's own copy. The
put's first touch of each of tens of thousands of parts was most of what was left (48 ms of 50); they are handed over as
they are made instead.

## Decisions

- **D1. Split by the page's order.** Taken up, the selection's first and last places in the page's order (`lo`,
  `hi`) cut the page in three: BEFORE (places under `lo`), BETWEEN (places from `lo` to `hi`, the selection and any
  stroke among them that is not selected), AFTER (places over `hi`).
- **D2. Before, drawn once.** The strokes before are drawn once, with the page's own draws limited to their span, into
  a picture of the working canvas's size. Every stroke drawn after it in a frame is later in the order, so a frame
  starts from that picture with a depth buffer that holds nothing.
- **D3. Between, drawn each frame.** Each frame draws the between span (the selection moved where it lies, and the
  strokes among it) with the page's own draws onto the before picture, in the area the selection was and is.
- **D4. After, kept as what it does.** Taken up, the after span is drawn once on its own: where one of its pens lies
  the pixel's color is fixed whatever is under it (kept, with a mask of where its pens lie). Where none of its pens
  lies, its highlighters and grain and wash strokes are drawn again each frame over the between draw, in the area
  the selection was and is, depth tested as the page draws them. Then the fixed colors are put where the mask says.
- **D5. Exact, or as now.** A frame is the page's own fold, step for step, so it is pixel for pixel what the whole
  draw shows. It is proven so (D7); anything that cannot be (a view moved while held, the card lost, a stroke cut)
  falls back to the draw as it is now.
- **D6. Memory.** The before picture, the after colors and the after mask: working-canvas textures made when a
  selection is taken up and destroyed when it is let go.
- **D7. Proof and measure.** On the maintainer's heaviest page (a copy, deleted after): each frame of a drag compared
  with a whole draw of the page with the selection where the frame put it, 0 pixels different, for a highlighter
  moved over and under pens, a pen moved over and under highlighters, washes and pencil, and selections mixed
  through the page's order. Each stage's time on the integrated card, in ms a frame, before and after.
