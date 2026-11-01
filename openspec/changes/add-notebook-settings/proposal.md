# Proposal: add-notebook-settings

## Why

The tablet keeps a setting per document for its cover: the first page, or the page last visited. PaperDaemon draws
covers by that setting but offers no way to change it, so a notebook whose cover shows the wrong page has to be changed
on the tablet.

## What Changes

- The viewer's title bar gets a settings button for the open document (a notebook, a PDF or a book), in both mirrors.
  It opens the document's settings: its cover, the last page visited or the first page.
- The False Mirror writes the setting into the document's own files at once.
- The Mirror writes it as the tablet stores it (the document's `coverPageNumber`), in place, with a page's safety: only
  while Edit the Mirror is on, never over a tablet change PaperDaemon has not pulled, the document backed up first.
  It is then sent to the tablet. With Edit the Mirror off, the setting is shown and says how to change it.
- The cover is drawn again for the page it now shows.

## Impact

- Affected specs: tablet/notebook-settings (new).
- Code: paperdaemon/remarkable/local.py, paperdaemon/remarkable/inplace.py, paperdaemon/server.py (the cover route and
  the setting in the library's list), paperdaemon/ui/tablet.js, the interface strings in every language.
