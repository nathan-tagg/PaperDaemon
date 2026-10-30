# Tasks

## 1. Writing a tablet page in place

- [x] 1.1 The in-place writer: untouched blocks kept, tombstones, new strokes, pieces, typed text by the CRDT, anchors kept
  (`remarkable/inplace.py`; the scene's ids from `local.scene_of`; the API's `mirror-scene` and `push` endpoints;
  checked on copies of the benchmark's pages in `tests/test_mirror_inplace.py`)
- [ ] 1.2 Check: every page of the calibration notebook and the test pages read, edited and read back; untouched blocks byte for byte

## 2. Safe to write

- [x] 2.1 The cloud check before each write; the editor told when the tablet changed the page first (the engine's side:
  `inplace.check_cloud`, answered as `reason: "tablet"`; the editor's: the reason shown, the page read again as it is)
- [x] 2.2 A backup of each document before its first write

## 3. The Mirror editable

- [x] 3.1 The Mirror's pages open with the editor's tools (`ui/tablet.js`; `ui/editor.html` reads them with their ids
  from `mirror-scene` and writes them in place on Ctrl+S, the document closed and the page left with changes, then
  pushes on Ctrl+S and close; what cannot be written in place is off there: the template, the page's own layers
  deleted or moved, typed text moved to another column)
- [ ] 3.2 Check on the real tablet with the maintainer (D4)
