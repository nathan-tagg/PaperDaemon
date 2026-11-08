## 1. PaperDaemon's author byte

- [x] 1.1 The tablet's limit, measured: notebooks with a page per author number (a layer, lettering and an erased
  stroke under each), up to one page per number from 1 to 512, pushed to the tablet
- [x] 1.2 The numbers the tablet opens a page with, mapped: 1-159, 175, 191, 207, 212 and 240-255; past 255 a page went
  as the byte its strokes carry (the number - 256), and a number the page's author table does not list opens all the
  same (render.TABLET_OPENS)
- [x] 1.3 The byte says whose and what (the maintainer's design): 100kkkkk, render.KINDS, author_of, is_own,
  kind_of_author, author_uuid; no setting and no record beside the page
- [x] 1.4 Strokes told what they are: Drawing.kind and tag, each step's strokes tagged when it is done (host and model
  steps), the reply's as written; write_rm numbers each kind on from its own ids
- [x] 1.5 The writers: notes (134; his layer taken up whatever author made it, notes laid as author 1 erased, no gap),
  typed text and checkboxes (136), pictures (135)
- [x] 1.6 The Mirror's whole-page save keeps the daemon's layer by its name
- [x] 1.7 Tests: the kinds and their bytes, the byte read back, strokes tagged by step, notes and job writes under
  their bytes; the replay re-recorded (only the author bytes changed)
- [ ] 1.8 A real run: a note, an answer, a highlight and a picture on a tablet page under their bytes, and the page
  opens there
