# Design: add-daemon-page-notes

## D1. Notes go up as copies, the last one in the page itself

While a job runs, the host reads and writes the page in the mirror. A note written into that page would go
up with the job's work before the job is recorded. So the notes during a job go up as copies of the page
as it was handed over, that page's file alone (`sync.push_doc(only=True)`). The last note goes into the
page itself once the host is done, and up with the next push.

## D2. The daemon's own author id

Everything the daemon writes carries the page's author number for PaperDaemon's notes (8 unless the page's author
table already ties another), registered in the page's author table beside the tablet's, the way a second device is,
and numbered past every counter on the page. (It was 218 until that left pages unreadable, then 134 until the tablet
was found to draw nothing under 128 and up.) Nothing is kept beside the page: until 11-11 a file, `daemon-ink.json`,
recorded what he laid on every page; once the notes' numbers changed under it, it hung erase marks on layers pages no
longer had, and the tablet drew nothing on them. The maintainer: "The daemon shouldn't need that."

## D3. Wipe his layer every time, keep one layer

Every write erases every stroke on his layer, whoever drew it, tombstoned as the tablet erases (the maintainer's word,
11-11: wipe it EVERY time). Two notes made from copies of the same page can share ids; if the tablet merges them while
the user writes, the next note wipes the layer and the page is clean again.

## D4. What the renderer leaves out

The renderer and the fingerprint leave out every stroke with the daemon's author id, wherever it is. They
also leave out every stroke lying directly on a layer named as his (the setting's name, or "PaperDaemon")
that he did not make. That covers his old notes and a layer the user named for him. The user's strokes on
his own layer are read. The page editor shows everything.

## D5. The running account

The host appends a line to `run/progress.json` (`events`) for what it read, for its plan, and for each
step as it ends. The daemon checks the file each second while a job runs. When it holds new lines, a copy
goes up with "On it" and the latest lines that fit the band (four rows). Lines that arrive together go up
as one note.

## D6. In the False Mirror

The False Mirror has no tablet to send a copy to, so its notes go into the page file itself, where its page editor
shows them; the host and the fingerprint never see them, as anywhere. "On it" is written before the host gets the
page and the last note after it is done. A note while the job runs is written only if the page is still as the daemon
read it: a page the host wrote in between keeps what it wrote, and that note is skipped.

The page editor shows his layer, and the user draws there too and keeps it (the maintainer's word, 11-07). The editor
takes in what the file gained and lost on his layer as on any other (his new note in, his last one out, the user's
strokes there staying), and keeps every stroke's id, False Mirror pages included: a save writes his layer's blocks
(its name, whether it shows, its place at the bottom) as he made them, his strokes under his byte as their ids say,
and the user's as the user's. Written anew under the editor's ids, his notes had once become the user's strokes: he
could not erase them, and made himself another layer each time. On a page from before his byte, the save that brings
the user's first stroke to his layer lays what the layer held again under the byte (notes.adopt on a Mirror page, in
place; the False Mirror writes those strokes under it), so his first note under it cannot take the user's stroke.
