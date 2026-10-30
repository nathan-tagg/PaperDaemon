# Tasks

## 1. The editor on WebGPU

- [x] 1.1 WGSL in `ui/shaders.js`: the stroke, highlighter, copy and shrink shaders, line for line
- [x] 1.2 The card module on WebGPU with today's interface (page, region, cut, replace, insertAfter, refresh, adopt, tidy, under; a floating selection's picture made and placed on the card, the screen read back for a fill, a capture and the thumbnail): chunks' records in draw order, batched draws, highlighters indexed, own strokes at their own depth; the processor's path when there is no WebGPU
- [x] 1.3 The WebGPU canvas shown; what is drawn over the page on a canvas laid over it
- [x] 1.4 The working canvas at the viewport's resolution (D7)
- [ ] 1.5 Check: the exactness suites (in place = whole = fresh, 0 px) on both cards, Direct3D 12 and 11; the timings of D3 against 0.1.85

## 2. A frame's work on the card

- [x] 2.1 Culling: each block's reach, packed in order, indirect draws (D4)
- [x] 2.2 The page's records boxed a block at a time on the card as they go up; a cut stroke's and an erase's pieces' records on the card, drawn in their place (D5)
- [ ] 2.3 The erase on the card: the test, what is left of each cut stroke, its pieces drawn at once and made strokes on the card as the swipe goes (D6) -- on in 0.2.0 on Direct3D 12, exact; in compatibility mode (Direct3D 11) the editor draws on the processor in 0.2.0 (D6: the compiler, the wait for the passes, exactness); next: the erase there, and a piece cut again kept in its stroke's room
- [ ] 2.4 Check: the exactness suites; erase frames on both cards against 0.1.85; a 250,000-stroke page within 200 MB

## 3. The engine on Dawn

- [x] 3.1 `tools/build_dawn.py`: Dawn built and carried with the engine; `tools/build_angle.py` retired
- [x] 3.2 `pipeline/page/gpu.py` on Dawn through a binding over `webgpu.h`, the WGSL from `ui/shaders.js`
- [x] 3.3 Check: the engine's pictures the same as the editor's, page for page

## 4. The Renderer setting

- [x] 4.0 The window started for its card: the engine finds the cards (`gpus.py`) and announces the web view's arguments; WebGPU's Direct3D 11 backend switched on where the card has no Direct3D 12 (D1)
- [x] 4.1 The machine's cards (DXGI: name, memory, Direct3D 12, Direct3D 11) and the default (D9)
- [x] 4.2 Settings: Renderer GPU / CPU, the card list, the "!"; the engine and the window use the card chosen
