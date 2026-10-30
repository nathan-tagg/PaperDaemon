# Proposal: move-renderer-to-webgpu

## Why

The page editor and the engine draw pages through WebGL2 (ANGLE on Direct3D 11). WebGL2 has no compute, so
the editor does its per-frame work on the processor: the eraser's test and cuts, deciding what to draw again,
and issuing the draws, about 4,300 WebGL calls a frame while erasing a page of 30,536 strokes. The browser's
graphics process then turns each call into Direct3D, more processor time. The maintainer's requirements: every
job that runs per frame, per stroke, per segment or per pixel belongs on the graphics card; every frame exact,
in real time, never under 60 frames a second, the next frame taking up what one could not finish; pages drawn
at the viewport's resolution and never below the tablet's; 200 MB of graphics memory up to 250,000 strokes;
the target machine a laptop a little weaker than a Ryzen 9800X3D's integrated Radeon; one shader source for the
editor and the engine.

A prototype measured the move on the maintainer's two cards (a high-end discrete Radeon and a Ryzen's integrated
Radeon), in WebGPU's full mode (Direct3D 12) and its compatibility mode (Direct3D 11), drawing the same records
as the editor: 0 pixels different from today in every case. A whole page took 3.07 ms of the discrete Radeon's time
and 1.64 ms after; 38.35 ms of the integrated Radeon's and 22.68 ms after. Drawing again an erase-sized area of
it took the integrated Radeon 14.47 ms, and 3.22 ms with culling done on the card.

## What Changes

- The editor draws with WebGPU: full mode on Direct3D 12, compatibility mode on Direct3D 11, chosen silently by
  what the card supports. WebGL2 is dropped. A machine with no WebGPU draws on the processor.
- WGSL is the one shader source, for the editor and the engine. The engine draws with Dawn, the WebView's own
  WebGPU implementation, built and shipped as PaperDaemon's ANGLE is today, so both draw alike.
- The work of a frame moves to the card: culling each segment against what is drawn, a card-side index of
  where the page's segments lie, the eraser's test, its cuts, and the drawing of what is left of a cut stroke.
  The pieces of a cut stroke are made from the card's own numbers when the swipe ends.
- Drawing: each chunk's records in draw order, its draws batched, a highlighter's shape from seven corners
  drawn indexed, each own stroke at its own depth.
- The working canvas is the viewport's resolution, never below the tablet's: the editor no longer draws twice
  the viewport each way when zoomed in.
- Settings: "Page drawing" becomes "Renderer", GPU (the default) or CPU; with GPU, a list of the machine's
  graphics cards, the default the Direct3D 12 card with the most memory, and a "!" beside a card with no
  WebGPU at all, saying pages will be drawn on the processor.

## Impact

- `paperdaemon/ui/editor.html` (its card module), `paperdaemon/ui/shaders.js` (WGSL),
  `paperdaemon/pipeline/page/gpu.py` (on Dawn), `tools/build_dawn.py` (new, replacing `tools/build_angle.py`),
  `paperdaemon/settings.py`, `paperdaemon/ui/settings.js`, `paperdaemon/server.py` (the cards), `shell/src/main.rs`
  (the window's card), the window's string files.
- What is drawn stays the same, pixel for pixel, except a zoomed-in view: it is drawn at the viewport's own
  resolution instead of twice that each way.
