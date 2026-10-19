# Design: add-epub-reading

## Context

Measured on 2026-10-18 and 19 from five test books uploaded through the desktop app and converted by the
maintainer's Paper Pro (tablet software on Qt 6.10.3), from the desktop app's program file, and from the library's
older PDFs (Qt 6.8.2). Where a finding is an inference, it says so.

## Findings

### F1. Who converts

- The desktop app files a book without a PDF: the `.epub`, a `.content` (`formatVersion` 1, `lineHeight` 100, a page
  count from its own layout, page ids) and a `.metadata` (`source` `com.remarkable.windows`). It keeps a local
  `.epubindex` it does not upload.
- The tablet lays the book out when it syncs it, uploads the PDF beside the `.epub` and writes its reading settings
  into the `.content` (`margins`, `textScale`, `lineHeight`, `textAlignment`, `fontName`). Every live book in the
  library has its PDF; the books without one are exactly those without a `margins` setting.
- The `.epub` stays; the PDF is added beside it. The tablet reads books without a PDF: it lays them out itself.
- The tablet treats the PDF as its own output (it moves an existing one aside and writes a new one when it lays a book
  out again). Inference: a PDF from elsewhere would be replaced.

### F2. The engine

The tablet's software (the desktop app is the same program, built for Windows) reads the book with its own EPUB code
and lays each spine item out with Qt's `QTextDocument`: one document per chapter, `setHtml`, a default style sheet,
`setDocumentMargin`, `setPageSize`, and the pages painted by Qt into a PDF (`QPdfWriter`).

### F3. The page

- Every book is laid out on 1404 x 1872 whatever the tablet; the PDF page is 445 x 594 pt (227 dpi).
- Document margin = the `margins` setting (125 by default), on all sides.
- Body: EB Garamond at 38 px times `textScale`, unhinted, design metrics, justified (`textAlignment`).
- Default style sheet: `p { line-height: <lineHeight>% } h1, h2, h3 { margin-top: 2em; margin-bottom: 1em }
  code { font-family: 'Noto Sans Mono' }`.
- The application font is reMarkable Sans at 16 px: Qt sizes the default sheet's `em` as the whole-pixel height of the
  rule's font at that size (19 for reMarkable Sans, 20 Ink Free, 16 Gabriola, 25 Segoe Script, 23 Comic Sans).
- Each chapter starts on a new page; a book ends with one blank page.

### F4. The book's own CSS (reMarkable's rewrite)

- `em` and `rem` (followed by `;` or white space), `pt` and `font-size` percentages become pixels of the body size:
  1em = 12pt = 100% = 38 px at scale 1.
- `line-height` goes from every rule but the headings': the reader's line spacing governs body text.
- `text-align: left` gives way to the reader's alignment; right and center stay.
- Pictures are set to the text width (1154 at margins 125), never taller than 1607: the page's text height less 15
  (measured once).

### F5. Faces

- A face the book carries (`@font-face`) is loaded and kept: the tablet keeps every face a book brought, for every book
  after it.
- A family the tablet has is used; otherwise the tablet's font matching decides: monospace names to Noto Sans Mono,
  serif names (`serif`, Times, Georgia, Palatino...) to its serif choice, everything else to Noto Sans. On a tablet
  with only its own faces the serif choice is Noto Sans Hebrew (whose full build carries Latin); once books have
  brought faces it may be one of them (Gabriola, measured), so it depends on what the tablet opened before.
- Qt's own `<pre>`, `<tt>`, `<kbd>` and `<samp>` name the family `monospace`, which lands on Noto Sans.
- reMarkable Sans is hinted to whole pixels; every other face is set unhinted.
- The faces: EB Garamond 1.000 (the desktop app's own build, not any published one), Noto Sans 2.015, Noto Sans Mono
  2.014 (both unhinted), Noto Sans Hebrew 3.001 (full), reMarkable Sans 1.500.

## Decisions

- **D1. Qt for Python, pinned to the tablet's Qt.** PySide6-Essentials 6.10.3 (LGPL, a library inside PaperDaemon, not
  a program it drives). Qt runs offscreen with a font folder of its own, so it sees only the tablet's faces, never the
  computer's. When the tablet's Qt changes, the version follows and the measurements are repeated.
- **D2. Measured result.** Against the five test books' tablet PDFs: same pages, and every glyph where the tablet put
  it, except (a) the weight-700 kerning inside bold words (this Qt build does not pass the variable font's weight to
  its shaper: up to about a unit per letter pair) and (b) a book that names a face it does not carry, after other books
  brought faces (F5). Accepted.
- **D3. PaperDaemon reads books in both mirrors; it converts in neither.** Pages are laid out on demand and the layout
  is cached. The real mirror uses the tablet's PDF once it is there and never gets a PDF from PaperDaemon. A PDF
  arriving on a book is not a page change: no job.
- **D4. The false mirror files books as the desktop app does** and keeps the faces books bring in its own font store
  (`<false-mirror-state>/fonts`); the serif choice there is Noto Sans Hebrew.
- **D5. Convert with the tablet** (false-mirror setting, shown only with a real mirror): a book imported into the false
  mirror is uploaded to the root of the tablet's library with the configured ignore tag; the daemon keeps a list of the
  books waiting; when the tablet's PDF arrives the PDF and the tablet's reading settings are copied into the
  false-mirror book and the tablet's copy is deleted outright (not to the trash). Turning it on warns that temporary
  books appear in the tablet's root and vanish, that a book converts only once a tablet is online, and that text may
  shift under ink already written on a book.
- **D6. Borrowed faces and templates need a signed-in account.** Without one, typed text and books use PaperDaemon's
  own faces (Noto Sans for reMarkable Sans, the published EB Garamond) and there are no templates: the Template
  control's hover text says to sign in, and pages that name a template show none. Signing in warns that typed text may
  shift slightly in the false mirror. A false-mirror setting goes back to PaperDaemon's own faces.
- **D8. A page is drawn as its own library shows it.** The renderer that draws a page for the window, the daemon and
  the host sets typed text and books in the faces of the page's library: the real mirror in the tablet's faces (and a
  book from the tablet's PDF when it has one), the false mirror in the faces its setting chooses (PaperDaemon's own,
  or the tablet's with an account). The page a lineup is shown, the free space it is given and the marks it erases
  are those of that drawing.
- **D7. Nothing reading a page depends on its face.** Harnesses, kits, skills and the host read rendered pages and
  typed text, never a face name.
