# Proposal: add-printing

## Why

The maintainer (11-23): "I want print functionality on a page / notebook. ctrl+p opens a modal when a notebook is open
(the editor). The modal gets the printers from windows, and has a page selector (range, single page, whole notebook
radios, with the page number selectors to the right of those radios."

## What Changes

- Ctrl+P in the page editor opens a print sheet: the printers Windows has (its default chosen); this page, a range or
  the whole notebook, each with its page numbers to the right; Cancel and Print. Nothing else.
- The engine draws each page as the tablet does and prints it through Windows itself (the spooler and GDI), no other
  program driven. A screen of the tablet is a sheet, fitted to the paper; a page written past its first screen runs on
  over as many sheets as it has screens.

## Impact

- `paperdaemon/printing.py`, `paperdaemon/server.py` (/printers, /library/{doc}/print), `paperdaemon/ui/editor.html`,
  `paperdaemon/ui/app.css`, the strings in 19 languages, `tests/test_printing.py`.
