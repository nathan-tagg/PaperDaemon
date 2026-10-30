# Proposal: add-pdf-text-selection

## Why

The tablet's recent firmware lets the pen select the text of a PDF or a book (EPUB) page to copy it. PaperDaemon's
editor cannot. The maintainer: "When I said highlighting, I meant selecting with the pen"; parity with the real
tablet is the bar.

## What Changes

- With the text tool (the I-beam) on a PDF or book page, a drag selects the document's own text, character by
  character as the tablet does, and Ctrl+C copies it. Nothing is written to the page.

## Impact

- `paperdaemon/ui/editor.html` (the selection and its drawing), a page's text layer from the engine
  (`paperdaemon/pipeline/page/pdf.py` with `pypdfium2`, already a dependency) and its endpoint in
  `paperdaemon/server.py`.
