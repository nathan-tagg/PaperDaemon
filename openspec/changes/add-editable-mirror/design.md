# Design: add-editable-mirror

## Decisions

- **D1. Written in place.** The writer starts from the page's own blocks, not from the editor's model. It keeps
  every block the user did not touch byte for byte; a stroke the user erased stays in the file with its value
  cleared and its length marked deleted (the tablet's tombstone), so its neighbors' links hold; a new stroke is
  added to its layer after the last one, under an id after the page's highest, by author 1; a piece of a cut
  stroke is a new stroke, its stroke a tombstone. Typed text is edited by the CRDT's own insertions and
  deletions. Ink in a group anchored to a paragraph stays in that group.
- **D2. Never over newer tablet work.** Before a page is written, its document's index is fetched from the
  cloud; if the page's file changed since PaperDaemon read it, nothing is written, the editor shows the page as
  it is now, and says so. The push already moves the library's root only by compare-and-swap on its
  generation.
- **D3. Backups.** Before PaperDaemon first writes a document of the Mirror, the document as it was is kept in
  the data folder, newest per document.
- **D1, as built.** `remarkable/inplace.py`. The editor reads a Mirror page with its ids (each stroke's item id and its
  group, each layer's node id, the place of each group drawn moved) and a stamp of the page's bytes, and saves it with
  that stamp. A stroke the save names by its id and leaves exactly as it was is kept; a stroke with no id, or one
  changed, is new; a new stroke that names a group anchored to the text goes into that group. What cannot be written
  in place exactly is refused with its reason, never guessed: a layer deleted or reordered, a new layer below the
  page's own, the text box moved, or typed text the page holds in a form that cannot be read exactly. A picture
  removed is a tombstone; one moved is a tombstone and a new item, as a moved stroke is; one added goes on the page's
  first layer. The daemon's layer is never written from the save.
- **D2, as built.** The check is one question to the cloud (`sync.cloud_file`): the page's file in the document's
  index now against the one last pulled or pushed. When the cloud cannot be asked, the page is not saved either. A
  page changed since the editor read it is refused the same way (its stamp). The editor's Ctrl+S and a document
  closed push the document by itself (`sync.push_edited`), not with the next job's push; while a job works on the
  notebook, the edit goes up with the job's work. The page as written is recorded in the job ledger as already seen,
  so the user's edit in the window is never taken for a request.
- **D3, as built.** The backup is `<data>/mirror-backups/<doc>`: every file of the document, copied before a write
  unless the document is still exactly as PaperDaemon itself last left it, so it is the document as the tablet last
  had it, and a newer copy replaces an older.
- **D4. Proven on the tablet.** Before release: pages with typed text and anchored ink, a PDF and a book, layers
  and pictures, drawn on, erased (passing, whole strokes, a zone), typed on and undone in the editor; each
  opened on the tablet and compared with the editor's.
