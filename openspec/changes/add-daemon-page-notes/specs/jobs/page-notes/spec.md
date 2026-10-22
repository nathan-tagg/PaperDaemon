# Spec Delta

## ADDED Requirements

### Requirement: The daemon writes on the page as he works
With Daemon notes on, the daemon SHALL write on the page it is handling: "On it" as soon as he hands the
job to the host, then each line the host reports (what it read on the page, its plan, each step as it
ends), then how the job ended. With the setting off, nothing SHALL be written on a page for a note.

#### Scenario: A job with two steps
- **WHEN** the host reads a page, plans two steps and finishes them
- **THEN** the tablet shows "On it", then what was read, then the plan, then each step, then "Done" with
  the time it took

### Requirement: Notes stay in the band above the safe area
Every stroke of a note SHALL lie in the band across the top of the page, above the safe area, under the
tablet's toolbar. A note too long for the band SHALL be cut, and a running account SHALL keep its first line
and its latest ones.

#### Scenario: A long account
- **WHEN** the host has reported nine steps
- **THEN** the note shows "On it" and the latest steps that fit, and nothing past the band

### Requirement: The daemon's strokes are his own
Everything the daemon writes on a page SHALL carry his own author id, registered in the page's author
table, with ids no other note of his on that page has used.

#### Scenario: Two copies of one page
- **WHEN** two notes go up as copies made from the same page
- **THEN** no stroke of the second has an id of the first's

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
The renderer and the fingerprint of a page SHALL leave out every stroke with the daemon's author id, and
every stroke on a layer with his layer's name that he did not make. Only the page editor SHALL show them.

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
