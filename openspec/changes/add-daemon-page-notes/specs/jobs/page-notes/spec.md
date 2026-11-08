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
Everything the daemon writes on a page SHALL carry the author byte of a daemon's note, 134 (see jobs/host,
"PaperDaemon's strokes say whose they are and what they were"), which the page's author table names; the tablet
writes as 1. His notes under the author they once had (218) left every page they were on unreadable on the tablet.
His ids SHALL be counted on from the highest of that author on the page and past the last he laid on any copy of it,
so that no note of his made from another copy of the page takes the same ids. What is his on a page SHALL be
everything under that byte and anything left under his old author, never judged by how its points look. The user's
strokes on his layer SHALL be the user's (the maintainer's word, 11-07: "let me draw on it and keep my strokes").
On a page from before his notes had a byte (its author table does not name it), everything on his layer SHALL be
his, his old notes there being the tablet's author, until his first note under the byte.

#### Scenario: Two copies of one page
- **WHEN** two notes go up as copies made from the same page
- **THEN** no stroke of the second has an id of the first's, and every stroke of both is of author 134

#### Scenario: Notes laid as the tablet's author
- **WHEN** a page holds a layer of his and notes on it written as the tablet's author (0.1.81 to 0.2.30)
- **THEN** the next note takes that layer up, never a second one, erases those notes, and goes up as author 134

#### Scenario: A page the old notes made unreadable
- **WHEN** a note is written on a page that still holds items under the daemon's old author (218)
- **THEN** every such item (strokes, tombstones, his old layer, its place, its entry in the author table) is taken out
  of the file, the user's strokes are kept as they were, and the page opens on the tablet again

### Requirement: Every write erases everything of his first
Before writing a note the daemon SHALL erase every stroke of his on the page, including strokes of notes
that went up in copies this page has never seen. He SHALL NOT erase the user's strokes on any layer, his own
included, but those the user wrote in his retry box.

#### Scenario: A copy that never saw the last note
- **WHEN** a note goes up made from a page that does not have the previous note
- **THEN** it carries the previous note's strokes erased, and the tablet's merge erases them

#### Scenario: Strokes on his layer
- **WHEN** the user has drawn on his layer, on the tablet or in the page editor, and a new note is written
- **THEN** only his strokes are erased; the user's stay, and are read as the page's

#### Scenario: The user's first stroke on his layer of a page from before his byte
- **WHEN** the page editor saves the user's first stroke on his layer of a page whose author table does not name his
  byte
- **THEN** what the layer held is laid again under his byte (the same strokes, exactly; a layer of his under his old
  author made anew), the page's author table names it, the user's stroke is the user's, and his next note takes his
  old note and leaves the user's stroke

### Requirement: The user draws on his layer in the page editor
The page editor SHALL let the user choose his layer and draw, erase and select on it as on any layer; it SHALL keep
his layer at the bottom of the list and never move it. A save SHALL write the user's strokes there as the user's and
keep his own under his byte; his layer's name and whether it shows SHALL stay as he made them. A note of his landing
on an open page SHALL replace his last one and leave what the user drew there, saved or not.

#### Scenario: A note lands while the user draws on his layer
- **WHEN** the user has drawn on his layer in the editor and a job's note lands before the editor saves
- **THEN** the editor shows the new note and the user's strokes, and its save writes both, each as whose it is

### Requirement: His layer
The daemon's notes SHALL be on one layer per page, named as the user chose (Settings: Daemon layer,
"Daemon" by default), at the bottom of the tablet's list of layers. A layer the user deleted SHALL be made
anew for the next note.

#### Scenario: The user deletes the layer
- **WHEN** the user deletes the daemon's layer on the tablet and a later job writes a note
- **THEN** the note is on a new layer

### Requirement: The renderer leaves his notes out
The renderer and the fingerprint of a page SHALL leave out every stroke of his: everything under his byte or his
old author, and on a page from before his byte everything on a layer with his layer's name (or the name his notes
once had, "PaperDaemon"). The user's strokes on his layer SHALL be read as the page's. Nothing SHALL be judged his by
how its points look. Only the page editor SHALL show his notes.

#### Scenario: A page with a note
- **WHEN** a note is written on a page
- **THEN** the page reads the same strokes and keeps the same fingerprint as without it

### Requirement: The retry box
A note for a job left skipped or failed SHALL carry a small box under its line, at the band's left like the
line and still in the band under the toolbar, with the word "retry" beside it. Anything the user writes in it,
found where the tablet draws it, SHALL hand the job over again, told that the user asked.

#### Scenario: Where the box sits
- **WHEN** a job is left skipped
- **THEN** its note's box sits under the note's line, at the band's left, inside the band

#### Scenario: A tick on a page with typed text
- **WHEN** the tablet stores the user's tick in a group anchored to the typed text
- **THEN** the tick is found in the box where it is drawn, and the job runs again

### Requirement: Retries
A job that failed SHALL go back in the queue on its own as many times as Settings: Retries allows (0 by
default), told how the last try ended. A page with nothing to do SHALL NOT be retried. A success SHALL start
the count again.

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
