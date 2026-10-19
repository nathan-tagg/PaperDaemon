# Tasks

## 1. The editor, as a working page

- [x] 1.1 Port `fastdecomp/render.c` and `render.py`'s stroke preparation to the page, and hold the page as page data (`docs/design/mockups/editor-v2.html`)
- [x] 1.2 `docs/design/mockups/editor-v3.html`: the tablet's two pickers and menus with PaperDaemon's own icons, the highlighter's six colors and the shader's eight, the eraser's two modes, typing with the three columns and four styles, lists, undo and redo across ink and text, frames to try every page size. Check: drawn, erased and typed headless on every frame, every screenshot looked at before hand-over Done: headless with the tablet's faces and with the substitute; text, lists, the narrow column, a passing erase, undo and redo, the 200 x 266 frame's clipping and the 0.5x view checked by eye.
- [ ] 1.3 The maintainer tries v3

## 2. Waiting on the maintainer or the tablet

- [ ] 2.1 D3: the pens' ink colors, the renderer's table or the tablet's
- [ ] 2.2 D6: read the style codes of the synced text test page and correct Header and Section
- [ ] 2.3 Read stored widths of every pen at each size from a synced page, replacing the placeholders
- [ ] 2.4 Read how the tablet stores the orange highlighter and the shader's colors
- [ ] 2.5 Choose the substitute family by measuring candidates against the tablet's faces

## 3. Templates

- [ ] 3.1 PaperDaemon reads the portrait templates itself, as it reads the fonts: the index, the definitions and the icon font out of the desktop app wherever it is installed (every Program Files, the user's programs folder, the uninstall entry's install location, the running app), and the rM Methods templates from the library; a renderer for the definitions, and the five drawn in code (Calligraphy, Hexagon) matched to the tablet
- [ ] 3.2 The template picker in the editor: one scrollable screen in the dialog, every template (defaults and rM Methods together, no tabs, no filter) as its icon over its name, the page's template underlined
- [ ] 3.3 D10: before any render a model sees includes a template, audit and fix every reader of a page (the model's render, layout and safe area, marks and erase grounding, OCR, the decomposer's input, the harnesses' and lineups' page descriptions), checked on real jobs

## 4. Into the app

- [x] 4.1 The editor in the page dialog, for the False Mirror's notebook pages (ui/editor.html; add-false-mirror)
