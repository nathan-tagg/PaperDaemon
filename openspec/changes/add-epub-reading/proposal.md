# Proposal: add-epub-reading

## Why

PaperDaemon has never read a book. It draws a book's pages from the PDF the tablet makes of it and uploads beside
the `.epub`; a book the tablet has not converted yet shows blank paper, and a book imported into the false mirror has
no tablet to convert it. 0.1.32 filled that gap by having Microsoft Edge print the book, which made PaperDaemon depend
on a browser the user may not have. That is gone: PaperDaemon lays books out itself, the way the tablet does.

## What Changes

- **PaperDaemon reads EPUBs.** A book's pages are laid out by Qt's text engine, set up the way the tablet sets it up
  (measured against the tablet's own PDFs; see design.md). It handles every EPUB it can: EPUB 2 and 3, any spine, its
  own CSS, fonts and pictures.
- **Real mirror:** a book is drawn from the tablet's PDF once the tablet has sent it, and from PaperDaemon's own layout
  until then. PaperDaemon never writes a PDF into the real mirror, and the tablet's PDF arriving never starts a job.
- **False mirror:** a book is imported as the desktop app files one (the `.epub`, its `.content` and `.metadata`, no
  PDF) and drawn from PaperDaemon's layout. Fonts a book carries are kept in the false mirror's own font store.
- **Convert with the tablet (optional, false-mirror settings):** for a user with a real mirror, a book imported into the
  false mirror is also sent to the root of the tablet's library, tagged with the configured ignore tag; when the tablet
  has converted it, its PDF is copied into the false-mirror book and the tablet's copy is deleted.
- **Borrowed faces and templates come with a signed-in account.** Without one: typed text and books in PaperDaemon's
  own faces, and no templates (the Template control says to sign in). Signing in warns that typed text may shift
  slightly in the false mirror; the false mirror can go back to PaperDaemon's own faces.
- **Edge removed** from the code entirely.

## Impact

- New `paperdaemon/remarkable/books.py` (the layout), `paperdaemon/content/book-fonts/` (open-licensed faces).
- `pyproject.toml`: PySide6-Essentials pinned to the tablet's Qt version (LGPL, shipped as a library).
- `remarkable/local.py` (import), `remarkable/fonts.py` (EB Garamond from the desktop app), `pipeline/page/render.py`
  and `thumbs.py` (drawing a book page), `remarkable/chapters.py`, the daemon (no job from a PDF), settings and the
  false mirror's settings section, the build.
