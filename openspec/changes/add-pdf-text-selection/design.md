# Design: add-pdf-text-selection

## Decisions

- **D1. Where the text is.** A PDF or book page: the engine reads the page's text layer with `pypdfium2` (every
  character and its box) and serves it in page units, in the frame the editor draws the page in (1404 units to
  157.5 mm, x centered on 0, y down from the page's top). A book's pages are PaperDaemon's own PDFs, or the
  tablet's, so they read the same way.
- **D2. Selection.** With the I-beam on a PDF or book page, a drag selects characters in reading order between the
  press and the pointer, whole lines between, the selection drawn as the editor draws its text selection; Ctrl+C
  puts the text on the clipboard, a line break between lines. Nothing is written to the page.
