# Design: add-daemon-page-notes

## D1. Every note goes into the page itself

Every note is written into the page in the mirror, under the page's lock, and that page's file alone goes up
(`sync.push_doc(only=True)`). Each note erases the last as the tablet erases and takes ids no note had. Until 11-11
the notes during a job went up as copies of the page as it was handed over: every copy numbered its note from the
same page, so each note took the ids of the last, and the job's work and its final note took them once more. The
tablet keeps an item it already holds, so its old notes stayed and piled up (four signatures over two Daemon layers).
The job's work goes up only with the job's end: once the host has written the page (its content fingerprint, which
leaves his notes out, differs from the page as handed over), a note during the job waits for the final one.

## D2. The daemon's own author id

Everything the daemon writes carries the page's author number for PaperDaemon's notes (8 unless the page's author
table already ties another), registered in the page's author table beside the tablet's, the way a second device is,
and numbered past every counter on the page. (It was 218 until that left pages unreadable, then 134 until the tablet
was found to draw nothing under 128 and up.) Nothing is kept beside the page: until 11-11 a file, `daemon-ink.json`,
recorded what he laid on every page; once the notes' numbers changed under it, it hung erase marks on layers pages no
longer had, and the tablet drew nothing on them. The maintainer: "The daemon shouldn't need that."

## D3. Wipe his layer every time, keep one layer

Every write erases every stroke on his layer, whoever drew it, tombstoned as the tablet erases (the maintainer's word,
11-11: wipe it EVERY time).

## D4. What the renderer leaves out

The renderer and the fingerprint leave out every stroke with the daemon's author id, wherever it is. They
also leave out every stroke lying directly on a layer named as his (the setting's name, or "PaperDaemon")
that he did not make. That covers his old notes and a layer the user named for him. The user's strokes on
his own layer are read. The page editor shows everything.

## D5. The running account

The host appends a line to `run/progress.json` (`events`) for what it read, for its plan, and for each
step as it ends. The daemon checks the file each second while a job runs. When it holds new lines, a note
goes up with "On it" and the latest lines that fit the band (four rows). Lines that arrive together go up
as one note.

## D6. In the False Mirror

In the False Mirror the notes go into the page file the same way and go nowhere else; its page editor shows them; the host and the fingerprint never see them, as anywhere. "On it" is written before the host gets the
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
