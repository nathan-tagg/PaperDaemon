# Proposal: add-editable-mirror

## Why

The maintainer wants the tablet's own library, the Mirror, editable in PaperDaemon's page editor: the 0.2.0
release. Today only the False Mirror's pages are; the Mirror's open without tools. The editor's save was made for
the False Mirror, PaperDaemon's own library: it writes the page anew from the editor's model, every layer and
stroke under new ids, and ink anchored to typed text written where it shows as plain ink. On a tablet page that
would replace the page's history and unhook handwriting from the text it follows.

## What Changes

- The Mirror's pages open with the editor's tools, as the False Mirror's do.
- A tablet page is written in place: what the user did not change is kept exactly as the tablet wrote it, a
  stroke erased is marked deleted as the tablet marks it, new strokes are added, typed text is edited as the
  tablet edits it, and anchored ink stays anchored.
- Before each write the page is checked against the tablet's library in the cloud; a page the tablet changed
  since it was read is never written over. Each document is backed up before PaperDaemon first writes it.
- Edits reach the tablet as PaperDaemon's own writes do, by its sync.

## Impact

- `paperdaemon/remarkable/inplace.py` (the in-place writer), `paperdaemon/remarkable/local.py` (the page read with
  its ids), `paperdaemon/remarkable/sync.py` (the check and the push), `paperdaemon/server.py` (the editor's
  endpoints), `paperdaemon/ui/tablet.js` and `ui/editor.html` (the Mirror's pages with tools).
- `openspec/changes/add-false-mirror/specs/tablet/false-mirror/spec.md`: "Editing is found in the false mirror"
  changes to match.
- Needs a real run on the maintainer's tablet before release.
