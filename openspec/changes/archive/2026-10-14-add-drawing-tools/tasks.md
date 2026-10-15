# Tasks

## 1. The renderer

- [x] 1.1 Port the renderer with both framings, the tablet page and cropped to the ink; verify against the pipeline's renders of fixture pages holding typed text, every pen, a picture and anchored items, and PDF pages of two sizes (157.5 × 210 mm and Letter) whose ink the tablet wrote Done, and replaced by ONE renderer in C (`fastdecomp/render.c`, `pipeline/paint.py`) that draws pages, page pictures, previews and drafts: the tablet's rule (a pixel's center inside the exact shape), `tests/test_render.py`; set beside the desktop app's own thumbnails of a calibration page and a decomposed portrait, alike. The pencil's grain is the device's and is not drawn.

## 2. Words

- [x] 2.1 Port the typeface measurement and the typed-column layout; find the reMarkable desktop app's fonts on the user's machine; verify an answer's line breaks match the pipeline's on fixture pages Done: the app's faces copied from the installed reMarkable desktop app at run time (`remarkable/fonts.py`, `tests/test_fonts.py`); `page/typed.py` measures and draws with them.
- [ ] 2.2 Choose and bundle the openly licensed substitute typeface with its license; verify answers wrap to the same column without the desktop app installed Superseded: the maintainer's faces are copied from the desktop app on the user's machine; without them typed text is drawn in the stroke lettering, and no substitute typeface ships.
- [x] 2.3 Draw bold; verify no formatting symbols reach the page Done: the model's markdown becomes bold, italic and heading lettering, never its symbols (`tests/test_ask.py`).

## 3. Charts

- [x] 3.1 Port the chart tool with its type set and refusals; verify every chart type renders offline Done: `pipeline/charts/` (56 types), every sample spec rendered offline and pinned by hash (`tools/baseline.py`, `tests/baseline/charts.json`).
- [x] 3.2 Keep the data's order and a light palette; verify with non-alphabetical categories and a single-series chart Done: `tests/test_charts.py` (categories in the data's order).
- [ ] 3.3 Insert charts as pictures filling their box's width, replacing a chart in the same place; verify on fixture pages
- [x] 3.4 Port the month calendar and week view, taking holidays and weather from the location setting; verify with no location and with one Done: `tests/test_charts.py` (a month with and without the user's place, offline).

## 4. Pictures and the decomposer

- [x] 4.1 Copy the decomposer engine and add the golden test against the pipeline's output on a fixed picture set; the test passes Done: the decomposer is ported to C, identical to the reference (`tests/test_decompose_identity.py`, corpus 30/30 and 90/90).
- [ ] 4.2 Trace generated and fetched pictures into their box; verify the aspect is kept
- [x] 4.3 Clean and insert coloring pages, with extra pages on new pages; verify a gray-shaded input comes out black and white Done: a coloring page is pure black lines on white, its extra pages right after the page that asked (the maintainer's rule for everything a job makes; `tests/test_ask.py`, `tests/test_inline_games.py`).
- [ ] 4.4 Verify no generated picture remains in the data folder after a job

## 5. Mark-ups, erasing and documents

- [ ] 5.1 Port located-word mark-ups for typed and handwritten words, never on the request; verify on fixture pages
- [ ] 5.2 Port PDF word finding and highlight placement; verify on fixture PDFs of two page sizes
- [x] 5.3 Port tombstone erasing; verify with a fixture page that no un-erased stroke moves Done: `tests/test_erase_tombstone.py` (the erased stroke a tombstone with its id and links, the others unmoved).
- [ ] 5.4 File documents as PDFs beside the inbox notebook, creating missing folders on its path; verify with a stubbed cloud

## 6. Real-run evidence

- [ ] 6.1 With the maintainer's go-ahead, run the maintainer's chart, picture, coloring page, mark-up and calendar dogfood cases through PaperDaemon and compare each page on the tablet with the pipeline's result; record the outcome here
