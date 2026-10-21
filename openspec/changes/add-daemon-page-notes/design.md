# Design: add-daemon-page-notes

## D1. Notes go up as copies, the last one in the page itself

While a job runs, the host reads and writes the page in the mirror. A note written into that page would go
up with the job's work before the job is recorded. So the notes during a job go up as copies of the page
as it was handed over, that page's file alone (`sync.push_doc(only=True)`). The last note goes into the
page itself once the host is done, and up with the next push.

## D2. The daemon's own author id

The tablet merges every version of a page it receives. Two notes with the same item ids, made from two
copies, merge into a mess. Everything the daemon writes carries its own author number (218), registered in
the page's author table beside the tablet's, the way a second device is. Its ids count upwards per page in
`daemon-ink.json`, a file only the daemon writes; the host saves the ledger as it works and could lose a
count kept there.

## D3. Erase everything of his first, keep one layer

Every write first erases every stroke of the daemon's on the page, tombstoned as the tablet erases. That
includes the strokes of copies this page has never seen: they are recorded, and their tombstones go with
every later write, until a page shows them erased. Notes from 0.1.52, on a layer named "PaperDaemon" with
the tablet's ids, are erased the same way.

The layer itself is kept, one per page. The tablet writes the user's strokes on whatever layer is
current, and the user's handwriting was found on the daemon's layer. Deleting that layer would take the
user's writing with it. The layer is made once and sent whole with every note (the same blocks and ids),
so copies merge into one layer. It goes at the bottom of the tablet's list of layers. If the user deletes
it on the tablet, the next note makes a new one.

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
