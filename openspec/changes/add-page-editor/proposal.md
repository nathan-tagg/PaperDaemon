# Proposal: add-page-editor

## Why

PaperDaemon shows the user's pages but cannot change them by hand. A page editor in the window lets the
user draw, erase and type on a page as on the tablet, and writes what they made as real page data. It
is also the start of a PaperDaemon library that needs no tablet at all: pages made in the editor are
ordinary `.rm` pages, so a user without a tablet or an account can still make pages and run PaperDaemon
on them.

Building it meant measuring how the tablet itself treats pages, pens and typed text, through the
tablet's screen share and its own files. Those findings are recorded here, because the renderer, the
layout and the editor all have to follow them.

## What Changes

- New capability `tablet/pages`: what a page is on the tablet. Its frame, its fixed units, the drawable
  square, how ink and text beyond it are kept but not shown, the three typed-text columns, and how a page
  opens.
- New capability `drawing/page-editor`: the editor in the page dialog. Two pen pickers and their
  menus as the tablet has them, the eraser, typing straight onto the page, the column setting, undo and
  redo, zoom, and pages written as `.rm` data drawn by PaperDaemon's own renderer.
- `drawing/text`: typed text drawn in the window uses the tablet's faces when the user's desktop app
  provides them, and otherwise an openly licensed family chosen to wrap like them.

## Impact

- `docs/design/mockups/editor-v3.html`: the working editor, for the maintainer to try before it joins the
  app.
- `paperdaemon/pipeline/page/typed.py` already lays text out in fixed units and wraps to any stored
  width; nothing in it changes.
- Two findings wait on the maintainer and change nothing yet: the pens' ink colors (design.md, D3), and
  which stored style code each of the tablet's four text buttons writes (D6).
