# Tasks

## 1. Reading books

- [x] 1.1 `remarkable/books.py`: the tablet's layout (design.md F2-F5) over PySide6, offscreen, its own font folder
- [x] 1.2 Faces: EB Garamond from the desktop app (`fonts.extract`); Noto Sans, Noto Sans Mono, Noto Sans Hebrew and
      the published EB Garamond shipped in `content/book-fonts` with their licenses
- [x] 1.3 A book page drawn from the layout where there is no PDF (`render.source_page`, thumbnails, chapters)
- [x] 1.4 The tablet's PDF never starts a job (test)
- [x] 1.5 `tools/check_books.py`: lay out books of the mirror and compare with the tablet's PDFs, glyph by glyph

## 2. The false mirror

- [x] 2.1 Import files a book as the desktop app does; Edge removed everywhere
- [x] 2.2 The false mirror's font store
- [x] 2.3 Convert with the tablet: the setting, its warning, the upload with the ignore tag, the waiting list, the
      PDF copied back, the tablet's copy deleted
- [x] 2.4 The setting to keep PaperDaemon's own faces

## 3. Accounts

- [x] 3.1 Borrowed faces and templates only with an account; the Template control's sign-in hover text
- [x] 3.2 The warning when adding an account

## 4. Packaging

- [ ] 4.1 PySide6-Essentials in the build (offscreen platform plugin), license notices

## 5. Proof

- [x] 5.1 The five test books agree with the tablet's PDFs (D2) Done: tools/check_books.py: tests 2, 4, 5 every page exact apart from bold kerning; 1 the same with one line shifted by it; 3 differs where the tablet used faces another book brought
- [ ] 5.2 A real book uploaded today and converted by the tablet agrees
- [ ] 5.3 Convert with the tablet, end to end on the real tablet
