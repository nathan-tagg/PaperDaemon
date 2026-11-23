# Spec Delta

## ADDED Requirements

### Requirement: The daemon writes on the page as he works
With Daemon notes on, the daemon SHALL write ONE message on the page it is handling, one line, rewritten each
time: when he saw the job, as soon as he hands it to the host; then what the host is doing now (the latest thing it
reports); then how the job ended (finished, failed or skipped, with the time it took). With the setting off, nothing
SHALL be written on a page for a note.

#### Scenario: A job with two steps
- **WHEN** the host reads a page, plans two steps and finishes them
- **THEN** the page shows one line: "Saw it" with the time, then "Now:" with the latest step, then "Finished" with
  the time it took, each replacing the last

### Requirement: Notes stay in the band above the safe area
Every stroke of a note SHALL lie in the band across the top of the page, above the safe area, under the
tablet's toolbar. A note SHALL never wrap: one too long for its line SHALL be cut where the signature begins.

#### Scenario: A long account
- **WHEN** the host has reported nine steps
- **THEN** the note is one line with the latest step, and nothing past the band

### Requirement: The daemon writes as the daemon's note
Everything the daemon writes on a page SHALL carry the page's author number for PaperDaemon's notes (see jobs/host:
8, unless the page's author table already ties another number to PaperDaemon's id for notes), which the page's author
table names; the tablet writes as 1. His notes under the author they once had (218) left every page they were on
unreadable on the tablet. His ids SHALL be numbered past every counter on the page. NOTHING SHALL be kept beside the
page about what he wrote there (the maintainer's word, 11-11: "The daemon shouldn't need that"): the page itself says
which numbers are free.

#### Scenario: Notes laid as the tablet's author
- **WHEN** a page holds a layer of his and notes on it written as the tablet's author (0.1.81 to 0.2.30)
- **THEN** the next note erases those notes (every machine-drawn stroke on that layer), keeps the user's strokes
  there, and goes up under the notes' number

#### Scenario: A page the old notes made unreadable
- **WHEN** a note is written on a page that still holds items under the daemon's old author (218)
- **THEN** every such item (strokes, tombstones, his old layer with whatever is on it, its place, its entry in the
  author table) is taken out of the file, the user's strokes elsewhere are kept as they were, and the page opens on
  the tablet again

### Requirement: One page, his writing known by its author
The daemon SHALL write his notes on the page's own first layer and SHALL make no layer of his own (the maintainer's
ruling, 11-22: "stop doing a separate layer for the daemon message ... One page, the daemon / models know what is on
the layer ... the stroke author is sufficient to know the daemons writing"). Every time he writes to a page (each
note, and the erase before a job) he SHALL erase his earlier notes by their author alone, wherever they are, and
nothing else but what the user wrote in his retry box. A layer named "Daemon" that a page already has SHALL be an
ordinary layer: the user's strokes on it are the page's, read by every job and kept by every note. Only on a page from
before his notes had an author of their own SHALL his old layer's machine-drawn strokes (his old notes) be erased as his.
A page with no layer at all SHALL get one, named as the tablet names its first.

#### Scenario: The user writes on the old Daemon layer
- **WHEN** the tablet's layer in use is a page's old Daemon layer and the user writes a request there
- **THEN** the job reads the request, and no note erases it

#### Scenario: A note replaces the last
- **WHEN** a second note is written on a page
- **THEN** the first note's strokes are erased by their author, the second is on the page's first layer, and the page's
  list of layers is as it was

### Requirement: The renderer leaves his notes out
The renderer and the fingerprint of a page SHALL leave out every stroke of his: everything under his notes' author
or his old author, and on a page from before his notes had an author, his old notes on his old layer. The user's
strokes on any layer SHALL be read as the page's. Only the page editor SHALL show his notes.

#### Scenario: A page with a note
- **WHEN** a note is written on a page
- **THEN** the page reads the same strokes and keeps the same fingerprint as without it

### Requirement: The retry box
A note for a job left skipped or failed SHALL carry a small box on the note's own line, right-aligned at the band's
right end after the signature, with the word "retry" beside it (the maintainer's word, 11-11: under the line, at the
band's left, it sat under the tablet's always-on dot). A note too long for its line SHALL be cut before the signature
and the box. Anything the user writes in the box, on any layer, found where the tablet draws it, SHALL hand the job
over again, told that the user asked.

#### Scenario: Where the box sits
- **WHEN** a job is left skipped
- **THEN** its note's box sits on the note's line, after the signature, at the band's right end, inside the band

#### Scenario: A tick on any layer
- **WHEN** the user ticks the box, on whatever layer the tablet has in use
- **THEN** the tick is found and the job runs again, and the next note erases the tick with the last note

#### Scenario: A tick on a page with typed text
- **WHEN** the tablet stores the user's tick in a group anchored to the typed text
- **THEN** the tick is found in the box where it is drawn, and the job runs again

### Requirement: Retries
A job that failed SHALL go back in the queue on its own as many times as Settings: Retries allows (0 by
default). The try after a failure -- the settings' or the retry box's -- SHALL be told what did not happen first, and
the request the failed try read, in the user's words, to carry out even where the page no longer shows it (11-21: a
retry found a blank page and skipped). A page with nothing to do SHALL NOT be retried. A success SHALL start the count
again. A handwritten or typed request SHALL stay on the page whenever a step answering it failed.

#### Scenario: Two retries allowed
- **WHEN** a job fails three times with Retries set to 2
- **THEN** it is tried twice more, then left

### Requirement: Handwriting is read where it is drawn
The host SHALL map the words the reader finds in a page's picture to page points from the picture's own
origin, so that a page written past its frame, or with ink left of it, is read where its marks are.

#### Scenario: A page longer than its frame
- **WHEN** the page's picture is taller than the frame
- **THEN** each word is given to the mark at its own page point

#### Scenario: A chat reply written above the box
- **WHEN** the player writes their reply on a messages page above the Message box
- **THEN** it is read as their message, from their ink alone, and all of it comes off once it is their bubble
