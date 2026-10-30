# Design: move-renderer-to-webgpu

## Context

The editor's card module (`GL` in `ui/editor.html`) holds the page's strokes in chunks: each chunk a buffer of
16-byte point records (x, y and width as floats; a byte of flags; the color), and a plan of draws in file order
(a run of pens, a run of highlighters, each shader or grain stroke on its own). A whole page is drawn into a
working canvas over what is under the ink, then shrunk to the screen (`FS_AREA`). An erase cuts strokes on the
processor and draws again the areas that changed, every stroke that can reach each area. The engine draws its
pictures with the same shaders through PaperDaemon's own ANGLE build.

The prototype that measured this design lives with the job that made it (WGSL ports of `shaders.js`, a batched
renderer, a tile renderer, culling); its numbers are below. Times are each card's own (timestamp queries,
Direct3D 12), in ms; the test page has 30,536 strokes (a decomposition with hand strokes of every pen over it,
1,219,722 points) at 1620 x 2160 working pixels.

## Decisions

- **D1. WebGPU, both modes, no WebGL2.** The window asks WebGPU for its card; it runs on Direct3D 12 where the
  card has it, and in compatibility mode on Direct3D 11 where it does not. Chromium (WebView2's engine, and
  Edge's) ships its Direct3D 11 backend switched off ("not fully implemented"), so on a card without Direct3D 12
  PaperDaemon starts the window's web view with it switched on, in compatibility mode: the engine finds the
  machine's cards (`gpus.py`) and names the web view's arguments in the line it announces itself with, and the
  shell starts the window with them. Nothing tells the user which mode. Without WebGPU the page is drawn on the
  processor (the editor's own CPU path; `render.c` in the engine). Every shader keeps within compatibility
  mode's limits (128 invocations a workgroup, 16 KB of workgroup memory, no plain `flat` interpolation, the
  vertex stage's storage buffers asked for), and anything the card refuses sends the page to the processor
  rather than drawing nothing.
- **D2. WGSL, one source.** `ui/shaders.js` holds the WGSL; the engine reads the same text. The engine draws
  with Dawn, built by `tools/build_dawn.py` and carried as ANGLE is today, through a thin binding of its own
  over `webgpu.h`. Measured: the WGSL drew the test page 0 pixels different from today's WebGL2 on both cards,
  in both modes.
- **D3. Drawing.** Each chunk's records stay in draw order, so a vertex reads its own record by its instance
  and never searches for its draw; consecutive draws of one kind in a chunk are one draw call; a highlighter's
  shape is its seven corners drawn indexed as the same three triangles; each own stroke (a shader's wash, a
  grain stroke) is at its own depth, so it decides each pixel once.

  | Whole page | discrete Radeon | integrated Radeon |
  |---|---|---|
  | WebGL2 (0.1.85) | 3.07 | 38.35 |
  | WebGPU, batched | 2.38 | 34.80 |
  | WebGPU, records in draw order, highlighters indexed | 1.64 | 22.68 |

  On the integrated Radeon a highlighter's cost was its vertices (the same with no pixels at all), and the
  prototype's first port searched for each vertex's draw: records in draw order removed both.
- **D4. Culling on the card.** All of the page's records lie in one buffer on the card, each chunk's from a block
  boundary (16 records a block). A part of the page drawn again (an erase, a stroke, a zoomed-in view) tests each
  block's box against the area in a compute pass, packs the blocks that reach it in file order (a prefix sum,
  so blending stays exact), and draws each batch from its stretch of that list with an indirect draw the card
  writes; the list's place travels in `firstVertex` / the base vertex, so core WebGPU suffices. A frame's areas
  share one list of the batches that can reach them; each area is culled on its own. Culling
  runs at every zoom wherever any of the page's ink lies outside what is drawn: a page scrolled at 1x, every
  erase and every stroke drawn again. Only a draw whose area holds every stroke skips the pass, where it could
  only cost time (a whole page in view: 2.11 culled against 1.65 on the discrete Radeon, 23.29 against 22.68 on the
  integrated Radeon).

  | Drawn | discrete Radeon | integrated Radeon |
  |---|---|---|
  | 128 x 128 px area, not culled | 1.18 | 14.47 |
  | the same, culled | 1.22 | 3.22 |
  | of that, the culling pass | 0.10 | 1.68 |
  | zoomed in 2x, not culled / culled | 1.41 / 1.73 | 21.43 / 19.97 |

- **D5. The page's records boxed on the card.** Each block of 16 records gets its box on the card as its records
  go up, so the culling pass tests a box per block, not every segment (testing every segment cost 1.68 ms of
  the 3.22 above). Measured, the whole cull of one area (the box test, the prefix sum, the packed list, the
  draws' arguments), median of 60:

  | Records on the page | discrete Radeon | integrated Radeon |
  |---|---|---|
  | 1.25 million (the test page, 30,536 strokes) | 0.018 | 0.29 |
  | 10 million (about 250,000 strokes) | 0.051 | 1.38 |

  Cells of the page were planned as the index; the blocks' boxes made them unnecessary. A stroke being cut and the
  pieces an erase made have their records on the card too, put up once as they change, and a chunk holding
  them draws them in their place, so no area of a swipe gathers records on the processor.
- **D6. The erase on the card.** The eraser's test of each segment near its path, and what is left of each
  stroke it cuts, are worked out on the card in a compute pass each frame; the cut strokes are drawn from that
  state at once, each piece as the file will hold it (its ends at the cuts, each piece of a wash at its own
  depth). The processor reads the state back once, when the swipe ends, and makes the pieces for the file and
  for undo from the card's numbers, so what is saved is what was shown. Measured, for the test alone, on the
  20,000 segments nearest the eraser: 0.004 ms on the discrete Radeon, 0.035 ms on the integrated Radeon (the
  processor's whole test and cuts: about 0.7 ms a frame on a Ryzen 9800X3D).

  On in 0.2.0 on Direct3D 12. A cut stroke is drawn by range, from its own records and its slot's kept
  stretches, so there is no draw and no bookkeeping per cut stroke. A slot the eraser has left alone for eight
  steps is made its pieces on the card (shaders.js ERASE: `flip`): each piece a stroke of its own, numbered from
  room the processor gave, put in the page's order where its stroke was (the order's edit read from the card's own
  counts). The card makes a log's worth of them a frame (about 230 strokes) and the processor takes each from the
  frame's answer; letting the swipe go makes the rest at once, so the processor no longer reads the whole swipe
  back when it ends. A fast flick that cut 22,000 of 30,000 strokes:

  | | all read back when the swipe ended | made as the swipe goes |
  |---|---|---|
  | done after the pen lifts, discrete Radeon | 328 ms | 124 ms |
  | done after the pen lifts, integrated Radeon | 327 ms | 130 ms |
  | processor per frame, p99 (discrete / integrated) | 2.07 / 2.12 ms | 1.93 / 2.13 ms |
  | card per frame (discrete / integrated) | 0.55 / 5.03 ms | 0.95 / 5.81 ms |

  The cost: a stroke cut again after its pieces were made takes new room for its slot, so a long back-and-forth
  swipe holds more graphics memory until it ends (the integrated card's peak on that flick: about 900 MB, against
  450). Next: a piece cut again kept in its stroke's room.

  In compatibility mode (Direct3D 11) the editor draws on the processor in 0.2.0. Direct3D 11's shader compiler
  (FXC) takes no workgroup atomic's value, which the stitch's data-parallel half and the spans pass use (an
  override can turn that half off there, and spans can sum each thread's share instead). It also takes about
  5.5 s over the erase's passes, and a swipe begun before they were ready lost the device. Once they were ready,
  480 pieces came out otherwise than the processor makes them and the page was 2,394 pixels off a whole redraw.
  Next: those, and then the erase on the card there too, as D1 has it.
- **D7. The viewport's resolution.** The working canvas is the viewport's size, or the tablet's resolution of
  what is shown where that is finer; never twice the viewport. Zoomed in 2x, the integrated Radeon drew it in
  14.92 ms where today's working canvas (twice the viewport each way) took 21.43, and holds a quarter of the
  pixels.
- **D8. On the screen.** The WebGPU canvas is the one shown; what is drawn over the page (the eraser's ring,
  the selection, the caret, the clear stroke) is drawn on a canvas laid over it. The page is no longer copied
  from the card's canvas to a 2D canvas and again to the screen.
- **D9. The card chosen.** The Renderer setting names a card by what it is (vendor, device, description), not
  by the LUID Windows gives it for a session. The engine finds it among the machine's cards (DXGI) at the start
  of each job; the window passes it to WebView2 when it starts (`--use-adapter-luid`), so a change of card
  reaches the window the next time PaperDaemon starts. A card counts as having WebGPU when Direct3D 12 or
  Direct3D 11 (feature level 11_0) can be opened on it.
- **D10. Tried and dropped.** Tile-based drawing on compute (each pixel resolved once from a sorted list of the
  shapes over its tile) was 1 pixel off and far slower: 11.97 ms a page on the discrete Radeon, 626.7 ms on the
  integrated Radeon; the card's rasterizer wins for strokes. Giving pens and highlighters a depth of their own
  to skip a stroke's repeats was exact but slower (the depth traffic cost more than it saved).

## Risks

- WebGPU on the target laptop (a Surface Laptop Go, Intel UHD Graphics): its Edge 156 reports WebGPU on
  Direct3D 12, with timestamps and indirect draws, so it runs the full mode. Compatibility mode covers Direct3D 11
  cards; a card with neither draws on the processor, and the setting says so.
- Dawn in the engine and in the WebView are separate builds; their output is proven the same page by page, as
  ANGLE's two builds are today.
