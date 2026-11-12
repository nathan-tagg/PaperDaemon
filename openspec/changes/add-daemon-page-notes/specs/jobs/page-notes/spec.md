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
where his layer is and which numbers are free.

#### Scenario: Notes laid as the tablet's author
- **WHEN** a page holds a layer of his and notes on it written as the tablet's author (0.1.81 to 0.2.30)
- **THEN** the next note takes that layer up, never a second one, erases those notes, and goes up under the notes'
  number

#### Scenario: A page the old notes made unreadable
- **WHEN** a note is written on a page that still holds items under the daemon's old author (218)
- **THEN** every such item (strokes, tombstones, his old layer with whatever is on it, its place, its entry in the
  author table) is taken out of the file, the user's strokes elsewhere are kept as they were, and the page opens on
  the tablet again

### Requirement: Every write wipes his layer
Every time the daemon writes to a page (each note, as he reports, and the erase before a job) he SHALL erase every
stroke on his layer, whoever drew it, and any note of his left elsewhere (the maintainer's word, 11-11: "It should not
care what is on that layer, it should wipe it EVERY time it wants to write something new to that layer"). He SHALL
NOT erase the user's strokes on any other layer, but those the user wrote in his retry box.

#### Scenario: Strokes on his layer
- **WHEN** the user has drawn on his layer, on the tablet or in the page editor, and a new note is written
- **THEN** everything on his layer is erased, the user's strokes there with it, and the note is written

### Requirement: The user draws on his layer in the page editor
The page editor SHALL let the user choose his layer and draw, erase and select on it as on any layer; it SHALL keep
his layer at the bottom of the list and never move it. A save SHALL write the user's strokes there as the user's; his
layer's name and whether it shows SHALL stay as he made them. His next note wipes the layer.

#### Scenario: A note lands after the user drew on his layer
- **WHEN** the user has drawn on his layer and a job's note is written
- **THEN** the layer holds the new note alone

### Requirement: His layer
The daemon's notes SHALL be on one layer per page, named as the user chose (Settings: Daemon layer,
"Daemon" by default), in the tablet's list of layers ONCE: a new one is added as the tablet adds a layer, last in
the list, and every write keeps one entry for it (the tablet's own, where it made one) and erases any other (11-11:
put first, the tablet put it in the list again, and every note showed on two Daemon layers). A layer the user deleted
SHALL be made anew for the next note.

#### Scenario: The layer in the list twice
- **WHEN** a page's list of layers holds his layer twice
- **THEN** the next write leaves it there once, and the tablet shows one Daemon layer

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
A note for a job left skipped or failed SHALL carry a small box on the note's own line, right-aligned at the band's
right end after the signature, with the word "retry" beside it (the maintainer's word, 11-11: under the line, at the
band's left, it sat under the tablet's always-on dot). A note too long for its line SHALL be cut before the signature
and the box. Anything the user writes in the box, on any layer, found where the tablet draws it, SHALL hand the job
over again, told that the user asked.

#### Scenario: Where the box sits
- **WHEN** a job is left skipped
- **THEN** its note's box sits on the note's line, after the signature, at the band's right end, inside the band

#### Scenario: A tick on his layer
- **WHEN** the user ticks the box with his layer chosen
- **THEN** the tick is found and the job runs again, and the next note wipes it with the layer

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
