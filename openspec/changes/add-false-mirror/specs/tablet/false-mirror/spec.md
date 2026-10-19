# Spec Delta

## ADDED Requirements

### Requirement: A false mirror is a library that never reaches the cloud
PaperDaemon SHALL let the user create a false mirror: a library kept only on this computer, holding the
same files a mirror of the tablet's library holds. Nothing in it SHALL be pulled from or pushed to the
cloud, and nothing in the tablet's mirror SHALL be read or written by the false mirror's work.

#### Scenario: A job in the false mirror
- **WHEN** a tagged page in the false mirror is answered
- **THEN** the answer is written to the false mirror's page and no request reaches the cloud

### Requirement: The daemon answers a false mirror as it answers the tablet
The daemon and the host SHALL treat a false mirror's pages exactly as the tablet's: the same tags,
sprompts, queue, notes and jobs, learning of changes from the false mirror's own files.

#### Scenario: A new page with a tag
- **WHEN** the user makes a page in a tagged notebook of the false mirror and writes a request on it
- **THEN** the daemon queues a job for it as it would for the same page on the tablet

### Requirement: The False Mirror is found by waiting
The Settings screen SHALL, after the user has stayed on it for 60 seconds without leaving, fade in a
False Mirror setting at its bottom. Its button SHALL open a dialog explaining that a false mirror is a
library on this computer only, answered by the daemon like the tablet's, and SHALL create one only on
confirmation. Once a false mirror exists, the setting SHALL show without the wait and SHALL offer to
delete it, in a dialog saying its notebooks will be gone, and SHALL delete it only on confirmation.

#### Scenario: Leaving too soon
- **WHEN** the user leaves Settings after 50 seconds and comes back
- **THEN** the count starts again and the setting is not shown

#### Scenario: Deleting the false mirror
- **WHEN** the user chooses to delete the false mirror and confirms
- **THEN** its daemon stops, its folders are removed, its tab leaves the rail, and the setting goes back
  to Create False Mirror; on a later visit to Settings it waits for the minute again

### Requirement: Making and moving things in the false mirror
The False Mirror tab SHALL offer New notebook, New page, Import and, for notebooks, Export, placed where
the screen's own controls are. Import SHALL take PDFs and EPUBs, several at a time, from the file chooser it
opens at once or from files dropped on the screen, each named by its file and landing in the folder open in the false
mirror; an EPUB SHALL be filed as the desktop app files a book, without a PDF, and read by PaperDaemon (add-epub-reading).
A long press on a notebook SHALL select it, and a menu with Export,
Move and Delete SHALL slide down from the top of the screen over the content, moving nothing on the
screen. Export SHALL write the notebook as a PDF. Tags on folders, notebooks and pages SHALL be set and
removed there, written as the tablet writes them. None of these controls SHALL appear in the tablet's
mirror, which SHALL keep showing tags as it does today (the folder's tag mark, the path's pills, the
covers' and the page's tags) without changing them.

#### Scenario: Importing into a folder
- **WHEN** the user has the folder Recipes open in the false mirror and drops a PDF and an EPUB on the screen
- **THEN** both become documents in Recipes, named by their files, and the book opens on its first chapter with its
  chapters listed

#### Scenario: Selecting a notebook
- **WHEN** the user presses and holds a notebook
- **THEN** the notebook shows as selected and a menu with Export, Move and Delete slides down over the
  top of the screen, and no notebook, folder or control on the screen moves

#### Scenario: The tablet's mirror
- **WHEN** the user presses and holds a notebook in the Mirror tab
- **THEN** nothing is selected and no menu appears

### Requirement: Editing is found in the false mirror
The page editor's controls SHALL show only on the false mirror's pages; pages of the tablet's mirror
SHALL open without them.

#### Scenario: A tablet page
- **WHEN** the user opens a page of the tablet's mirror
- **THEN** it shows as it does today, with no pens, eraser, text or layers controls

### Requirement: The rail names the mirrors
The rail SHALL name the tablet's library Mirror and, once one exists, show False Mirror directly below
it, the same screen over the false mirror's library.

#### Scenario: Creating a false mirror
- **WHEN** the user confirms the dialog
- **THEN** a False Mirror tab appears in the rail directly below Mirror
