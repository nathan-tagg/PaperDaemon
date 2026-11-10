## ADDED Requirements

### Requirement: The Mirror's pages can be edited
While Edit the Mirror is on in Settings (off until the user turns it on), a page of the tablet's Mirror SHALL open in
the page editor with its tools, as a False Mirror page does, and the user's changes SHALL reach the tablet by
PaperDaemon's sync. Off, the engine SHALL write none of the Mirror's pages. The setting SHALL say that PaperDaemon
cannot promise an edit never damages a notebook, above all after an update of the tablet's software. Each time the
user turns it on, a warning SHALL come first: editing the tablet's files with PaperDaemon raises the risk of damaging
them; it has been tested, but proceed with caution. Nothing remembers the answer; canceling leaves the setting off.

#### Scenario: A stroke drawn on a Mirror page
- **WHEN** the user draws a stroke on a Mirror page and leaves it
- **THEN** after the next sync the tablet shows the stroke where the editor showed it

#### Scenario: Turning editing on
- **WHEN** the user ticks Edit the Mirror, whether or not they turned it on before
- **THEN** the warning shows, and the setting is on only if they choose to turn it on there

### Requirement: A sync shows how far it has come
While a Mirror document's edits go up to the tablet (Ctrl+S, or the document closed), a thin bar SHALL show how far
the sync has come: under the viewer's bar while the document is open, along the top of its cover once it is closed.
It SHALL fill by the sync's requests to the cloud and be gone a moment after the sync is through; a sync that failed
SHALL leave no bar, its reason shown by the document's name.

#### Scenario: Closing an edited notebook
- **WHEN** the user closes a Mirror notebook they wrote on
- **THEN** a bar runs along the top of its cover until the edit has reached the cloud, then goes

### Requirement: A tablet page is written in place
Writing a tablet page SHALL keep every part of it the user did not change exactly as the tablet wrote it: its ids,
its layers, its typed text's history, and ink anchored to its text, still anchored. An erased stroke SHALL be
marked deleted as the tablet marks it, not removed. Everything new (a stroke, a typed character, a picture, a value
set) SHALL be numbered by an author of the editor's own: never the tablet's, so an edit made here and writing the
tablet has not yet synced cannot take the same ids; one the tablet opens; and not one of PaperDaemon's own, because
what is written here is the user's hand. Its ids SHALL be counted past the highest id any author holds on the page.
The page's author table SHALL be left as it is. A page whose typed text cannot be read in order (its items pointing
at each other, as two edits under one author's ids left them) SHALL say that it holds text it cannot read, SHALL
refuse an edit of that text, and SHALL take a save with no paragraphs by deleting every character where it stands.

#### Scenario: Erasing near anchored ink
- **WHEN** the user erases one stroke on a page whose handwriting is anchored to its typed text, and the text is
  later edited on the tablet
- **THEN** the remaining handwriting still moves with its paragraph on the tablet

#### Scenario: Written on the tablet at the same moment
- **WHEN** the user types on the tablet, and before the tablet has synced that typing the same page is typed on here
  and sent
- **THEN** the tablet holds both, each character under an id of its own, and neither is lost or moved into the other

#### Scenario: A text left tangled by an earlier version
- **WHEN** a page's typed text cannot be read in order and the save has no paragraphs
- **THEN** every character is marked deleted where it stands, the strokes and pictures are left as they are, and the
  page no longer says it holds text it cannot read

### Requirement: Newer tablet work is never written over
Before writing a page, PaperDaemon SHALL check the page against the tablet's library in the cloud; a page changed
on the tablet since PaperDaemon read it SHALL NOT be written over: the editor SHALL show the page as it is now and
say so. Each document SHALL be backed up before PaperDaemon first writes it.

#### Scenario: Edited on the tablet meanwhile
- **WHEN** the user edits a page in PaperDaemon while the same page was changed on the tablet and synced
- **THEN** PaperDaemon does not write its version, shows the tablet's, and tells the user
