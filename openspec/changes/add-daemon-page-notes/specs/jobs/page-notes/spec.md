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

### Requirement: The daemon writes as the tablet's own author
Everything the daemon writes on a page SHALL carry the tablet's own author id (1): the tablet does not open a page
that holds an item of an author it does not know, and his notes under an author of their own (218) left every page
they were on unreadable there. His ids SHALL be counted on from the highest of that author on the page with a wide
gap, so that no other note of his, and nothing the user adds on the tablet while a note goes up, takes the same ids.
What is his on a page SHALL be the machine-drawn strokes on his layer: every point at one pressure (190) with no
speed and no direction, which no hand on the tablet makes.

#### Scenario: Two copies of one page
- **WHEN** two notes go up as copies made from the same page
- **THEN** no stroke of the second has an id of the first's, and every stroke of both is of the tablet's author

#### Scenario: A page the old notes made unreadable
- **WHEN** a note is written on a page that still holds items under the daemon's old author (218)
- **THEN** every such item (strokes, tombstones, his old layer, its place, its entry in the author table) is taken out
  of the file, the user's strokes are kept as they were, and the page opens on the tablet again

### Requirement: Every write erases everything of his first
Before writing a note the daemon SHALL erase every stroke of his on the page, including strokes of notes
that went up in copies this page has never seen. He SHALL NOT erase the user's strokes, on any layer, but
those the user wrote in his retry box.

#### Scenario: A copy that never saw the last note
- **WHEN** a note goes up made from a page that does not have the previous note
- **THEN** it carries the previous note's strokes erased, and the tablet's merge erases them

#### Scenario: The user wrote on his layer
- **WHEN** the user's strokes are on the daemon's layer and a new note is written
- **THEN** the user's strokes stay, and are read as the user's

### Requirement: His layer
The daemon's notes SHALL be on one layer per page, named as the user chose (Settings: Daemon layer,
"Daemon" by default), at the bottom of the tablet's list of layers. A layer the user deleted SHALL be made
anew for the next note.

#### Scenario: The user deletes the layer
- **WHEN** the user deletes the daemon's layer on the tablet and a later job writes a note
- **THEN** the note is on a new layer

### Requirement: The renderer leaves his notes out
The renderer and the fingerprint of a page SHALL leave out every stroke of his: the machine-drawn strokes on a
layer with his layer's name (or the name his notes once had, "PaperDaemon"), and anything under his old author. What
a hand wrote on such a layer SHALL be read as the user's. Only the page editor SHALL show his notes.

#### Scenario: A page with a note
- **WHEN** a note is written on a page
- **THEN** the page reads the same strokes and keeps the same fingerprint as without it

### Requirement: The retry box
A note for a job left skipped or failed SHALL end with a box. Anything the user writes in it, found where
the tablet draws it, SHALL hand the job over again, told that the user asked.

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
