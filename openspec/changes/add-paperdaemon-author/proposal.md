# Proposal: add-paperdaemon-author

## Why

Every item on a page carries an author number. Since 0.1.81 PaperDaemon has written everything as the tablet's own
author (1), because its notes under an author of their own (218) left every page they were on unreadable on the
tablet. So nothing in a page said which strokes were PaperDaemon's, and its daemon told its notes from the user's
writing by how the strokes looked (machine-drawn points). The maintainer's ruling (11-07): telling PaperDaemon's
strokes from the user's by how they look is wrong; each stroke has an author.

Measured on the tablet (11-07), a page per author number from 1 to 512: a stroke keeps its author in ONE byte, and
the tablet opens a page with 1-159, 175, 191, 207, 212 and 240-255 and no other; past 255 a page went as the byte its
strokes carry, and a number the page's author table does not list opens all the same. The maintainer's design: the
byte itself says that a stroke is PaperDaemon's and what it was to PaperDaemon, with no record kept beside the page.

## What Changes

- Everything PaperDaemon writes is numbered 100kkkkk (128-159, all of which open): the top three bits say it is
  PaperDaemon's, the low five what it was -- 129 a written answer, 130 a picture traced into strokes, 131 a chart,
  calendar or table, 132 a sketch, 133 a mark-up, 134 the daemon's note, 135 a placed picture, 136 typed text (128:
  of no kind the host knows). Each kind numbers its own ids, so none meets another's or the tablet's.
- Each step's strokes are told what they are when the step is done; the page's author table names each byte used.
- The daemon's notes go up as 134: everything under it, or on his layer, is his. Notes laid as the tablet's author
  (0.1.81 to 0.2.30) are erased like any of his, and a layer of his made then is taken up, never doubled. The gap his
  ids kept above the host's is gone.
- The Mirror's whole-page save keeps the daemon's layer by its name, whatever author made it.

## Impact

- Affected specs: jobs/host (what a job writes); the page-notes requirements in add-daemon-page-notes are rewritten.
- Code: paperdaemon/pipeline/page/render.py (KINDS, author_of, is_own, kind_of_author, author_uuid),
  paperdaemon/pipeline/draw/__init__.py (Stroke, Drawing.kind and tag, write_rm by kind),
  paperdaemon/pipeline/daemon/notes.py, paperdaemon/pipeline/page/typed.py, paperdaemon/pipeline/page/images.py,
  paperdaemon/pipeline/host (the step loops, the reply), paperdaemon/remarkable/local.py.
