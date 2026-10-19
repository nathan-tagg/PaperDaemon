# Spec Delta

## ADDED Requirements

### Requirement: PaperDaemon reads books
PaperDaemon SHALL lay out an EPUB's pages itself, as the tablet lays them out: each chapter on its own pages of the
tablet's book page, the book's own CSS, faces and pictures applied as the tablet applies them, and the book's reading
settings (margins, text scale, line height, alignment) from its `.content`. It SHALL read EPUB 2 and EPUB 3 books and
every book it can, and SHALL say so, not draw blank pages, when it cannot.

#### Scenario: A book the tablet has not converted
- **WHEN** a book in the real mirror has no PDF yet
- **THEN** its pages are drawn from PaperDaemon's layout, with the book's text

#### Scenario: A book the tablet has converted
- **WHEN** the tablet's PDF of a book is in the real mirror
- **THEN** its pages are drawn from that PDF

### Requirement: A page is drawn as its own library shows it
Every drawing of a page (the window's, the daemon's and the one a lineup is shown) SHALL set typed text and books in the
faces of the page's own library, so that where the text is, is where that library puts it: the real mirror in the
tablet's faces and from the tablet's PDF when there is one; the false mirror in the faces its setting chooses.

#### Scenario: A false mirror in PaperDaemon's faces
- **WHEN** the false mirror is set to PaperDaemon's own faces and a job is answered on one of its book pages
- **THEN** the page the lineup is shown is laid out and drawn in PaperDaemon's faces, as the window shows it

### Requirement: PaperDaemon never converts a book in the real mirror
PaperDaemon SHALL NOT write a PDF, an index or reading settings into a book of the real mirror.

#### Scenario: Reading a new book
- **WHEN** PaperDaemon lays out a real-mirror book
- **THEN** nothing in the real mirror changes and nothing is pushed

### Requirement: A converted book is not a request
The tablet's PDF arriving on a book SHALL NOT start, queue or reopen a job, and SHALL NOT count as a change to any of
its pages.

#### Scenario: The tablet sends a book's PDF
- **WHEN** a pull brings the PDF and the reading settings of a book whose pages are unchanged
- **THEN** the daemon queues nothing for it

### Requirement: The layout matches the tablet's
Laid out with the tablet's faces, a book SHALL have the tablet's pages: the same page count and the same lines on each
page, glyphs where the tablet puts them, except where design.md (D2) records otherwise.

#### Scenario: The test books
- **WHEN** the five test books are laid out and compared with the tablet's PDFs of them
- **THEN** pages and glyph positions agree, apart from the kerning inside bold words
