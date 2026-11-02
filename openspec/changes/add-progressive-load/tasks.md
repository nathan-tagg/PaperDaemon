## 1. Reading and making

- [x] 1.1 The page's points in one array, a stroke's box worked out as it is read (sceneFromBytes, pointsOf)
- [x] 1.2 A stroke's part made in one walk along its points, its records in runs of one buffer (freshPart, recRoom):
  every part of the maintainer's 149,807-stroke page the same to the bit as the old maker's
- [x] 1.3 Measured (integrated card, clean copy, warm): the heavy page 1.64 s -> 1.06 s to shown, all at once

## 2. A frame at a time

- [x] 2.1 Paper, template and text first; strokes in the page's order, a frame's worth of points each frame (the frame
  before's cost a point), drawn over what came before (the card's order meanwhile just them: inkMore)
- [x] 2.2 The page's whole order made once the last are in (inkDone); a whole draw meanwhile draws what has come in
- [x] 2.3 Keys, presses and the wheel held until the strokes are in
- [x] 2.4 Proved: the page once in against a whole redraw 0 pixels, and against the old load's screen the same; its
  parts against the old maker's 0 of 149,807. Measured: shown after 0.23 s, all in after 1.15 s, 57 frames, the longest
  33 ms (the engine's answer warm; a page the engine has not read since it changed waits on it first, 1.9 s on that page)

## 3. The page before its strokes

- [x] 3.1 The engine's answer of a page without its strokes (form=head: local.scene_head), its stroke blocks skipped
  unread in C (fastrm.without_strokes over rf_rm_blocks): the same as the page read whole less its strokes; 29 ms on the
  heavy page, 220/220 pages the same bytes as the Python walk
- [x] 3.2 The editor shows it once the card has answered, the strokes asked for after it; the cover clear, no spinner

## 4. Opening without waiting on the page before

- [x] 4.1 New page: the blank page made without reading the page it follows (library._without_content): 13.3 s -> 72 ms
  after a 149,807-stroke page, 480/480 pages the same bytes
- [x] 4.2 The window holds the graphics card (core.js PD.holdCard): after a press on a page the next page compiled every
  shader again (0.9 s, the card 67 ms, integrated card); held, 4 ms and 8 ms
- [x] 4.3 A page's stamp is what its own form is made from (its .rm and what the notebook says of it); a page saved is
  made into its form at once, off the request; a page being written is read once written: opened again, 64 ms
