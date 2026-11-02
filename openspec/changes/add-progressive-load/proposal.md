# Proposal: add-progressive-load

## Why

Opening a heavy page waited for every one of its strokes to be read, made and put on the graphics card before any of it
showed: about 1.6 s on the integrated card for a 150,000-stroke page in a clean copy, much longer in the maintainer's
running app. The maintainer's ruling (2026-11-01): "However many strokes can load in one frame, load those, and if
theres still more, load them in the next frame. The user will at least see progress of the strokes appearing, but won't
try to mess with things. Picture first is a TERRIBLE idea."

## What Changes

- A page's paper, template and text show at once; its strokes come in, in the page's order, as many as one frame holds
  each frame, each frame's drawn over what came before. When the last are in, the page is what drawing it whole shows.
- Keys, presses and the wheel wait until the strokes are in.
- Reading and making a page's strokes cost less: one array for the page's points, a stroke's drawing data made in one
  walk along its points.
- No picture of the page is ever shown in its place.

## Impact

- Affected specs: drawing/page-editor.
- Code: `ui/editor.html` (loadPage, inkFrame, the card's inkMore and inkDone; sceneFromBytes, freshPart).
