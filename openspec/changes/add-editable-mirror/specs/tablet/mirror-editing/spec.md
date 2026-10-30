## ADDED Requirements

### Requirement: The Mirror's pages can be edited
A page of the tablet's Mirror SHALL open in the page editor with its tools, as a False Mirror page does, and the
user's changes SHALL reach the tablet by PaperDaemon's sync.

#### Scenario: A stroke drawn on a Mirror page
- **WHEN** the user draws a stroke on a Mirror page and leaves it
- **THEN** after the next sync the tablet shows the stroke where the editor showed it

### Requirement: A tablet page is written in place
Writing a tablet page SHALL keep every part of it the user did not change exactly as the tablet wrote it: its ids,
its layers, its typed text's history, and ink anchored to its text, still anchored. An erased stroke SHALL be
marked deleted as the tablet marks it, not removed; a new stroke SHALL be added under a new id by the tablet's own
author.

#### Scenario: Erasing near anchored ink
- **WHEN** the user erases one stroke on a page whose handwriting is anchored to its typed text, and the text is
  later edited on the tablet
- **THEN** the remaining handwriting still moves with its paragraph on the tablet

### Requirement: Newer tablet work is never written over
Before writing a page, PaperDaemon SHALL check the page against the tablet's library in the cloud; a page changed
on the tablet since PaperDaemon read it SHALL NOT be written over: the editor SHALL show the page as it is now and
say so. Each document SHALL be backed up before PaperDaemon first writes it.

#### Scenario: Edited on the tablet meanwhile
- **WHEN** the user edits a page in PaperDaemon while the same page was changed on the tablet and synced
- **THEN** PaperDaemon does not write its version, shows the tablet's, and tells the user
