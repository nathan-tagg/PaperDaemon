# Proposal

## Why

Everything a job leaves on a page is made by a drawing tool: an answer in the tablet's typeface, a
chart, a picture traced into strokes, a coloring page the user can color over, a highlight on a word, a
calendar filed as a document. The pipeline built and tuned each of these on real pages, and the
decomposer that turns pictures into strokes is the single largest piece of work in the prototype.
PaperDaemon needs them all, working exactly as they do in the pipeline and cleaned for publishing.

## What Changes

- **Words**: answers drawn as ink in the tablet's own typeface metrics, in the typed-text column, with
  bold where the answer uses it.
- **Charts**: the model supplies data and a chart type, never code; charts render offline, keep the
  data's order, and reach the page as pictures that fill their box's width. A month calendar and a week
  view are chart types.
- **Pictures**: generated or fetched pictures are traced into strokes by the decomposer; coloring pages
  are cleaned to pure line art and inserted as pictures the user can color and erase over.
- **The decomposer**: the pipeline's frozen engine, shipped unchanged.
- **The renderer**: a page drawn as the tablet shows it, whole for the model's page image and the
  benchmark, cropped to the ink for the decompose preview.
- **Mark-ups**: highlight, circle, underline or strike the words a request names, on pages and on PDFs.
- **Erasing** that keeps the page's structure, so nothing that was not erased moves.
- **Documents**: calendars and other multi-page results filed as PDFs beside the inbox notebook.

## Capabilities

### New Capabilities
- `drawing/text`: answers as ink in the tablet's typeface, placement and emphasis.
- `drawing/charts`: chart specs, rendering, order, placement, calendars.
- `drawing/pictures`: generated and fetched pictures, coloring pages.
- `drawing/decomposer`: turning a picture into pen strokes.
- `drawing/markups`: marking up located words, on pages and PDFs, and erasing safely.
- `drawing/documents`: documents made by a job, filed beside the inbox notebook.

### Modified Capabilities
None.

## Non-goals

- New chart types beyond the pipeline's set.
- Shipping the reMarkable app's fonts.
- Editing or reflowing the user's own typed text.

## Impact

- New package `paperdaemon/draw/`, ported from the pipeline's `rm_text`, `rm_typed`, `typed_layout`, `rm_chart`,
  `rm_images`, `rm_pdfdoc`, `rm_pdftext`, `rm_marks` and `rm_paint`.
- Dependencies: `vl-convert-python` (BSD-3-Clause) for charts, Pillow and numpy for pictures, and
  `rmscene` pinned at the version the pipeline uses for `.rm` files.
- The tablet's typeface is read from the user's reMarkable desktop app installation when present.
