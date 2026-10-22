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
A long press or a right-click on a notebook or folder SHALL select it, and while anything is selected a click
SHALL add an item to the selection or take it away; a menu with Export and Duplicate (notebooks only), Move, Tags and
Delete SHALL take the place of the library's title bar, as the tablet's action bar does, covering and moving nothing;
it has no Done: Esc lets the selection go. MOVE SHALL NOT open a sheet: the bar SHALL turn into where to, the folders
opening as ever, and in a folder the items are not all in already the bar SHALL offer Move here; Esc lets it go.
The page grid SHALL select pages the same way, its actions in the viewer's bar, as a
bar that acts on all of them: Select all, Duplicate (each copy right after its page), Move, Tags and Delete (for good,
after a confirm; a notebook keeps one page). Move SHALL turn the bar into where to: a page chosen in the grid, and the
bar SHALL offer Move before and Move after it, each with its icon; Move out SHALL leave the notebook for the library,
where the notebook opened shows its grid to choose in the same way. Esc in the grid SHALL step back one thing at a
time: the page chosen, the move, the pages chosen, then out of the grid to the page; the viewer closes from the page.
New notebook SHALL take tags. Export SHALL write the notebook as a PDF. Tags on folders, notebooks and pages SHALL be set and
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

#### Scenario: Deleting two pages
- **WHEN** the user right-clicks page 2 in the grid, clicks page 4, and chooses Delete and confirms
- **THEN** pages 2 and 4 are gone, and the pages after them move up

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

### Requirement: The false mirror syncs as the tablet does
In the false mirror the daemon SHALL see a page's ink as of the last sync: Ctrl+S in the page editor, or closing the
document. The editor SHALL keep saving as the user draws, and between syncs the daemon SHALL see each page as it was
at the last sync, never half drawn.

#### Scenario: Drawing, then Ctrl+S
- **WHEN** the user draws a request on a tagged false-mirror page and has not synced
- **THEN** no job starts; after Ctrl+S (or closing the document) the page is a job

### Requirement: The viewer's bar is the tablet's toolbar
On a page, the viewer's bar SHALL hold on its left the page editor's tools where the page can be edited (pen, pen,
text, eraser, layers; selection and capture, when they come, between eraser and layers), and on its right the tag
button, the page grid and the page arrows. In the page grid its right SHALL hold the chapters, the grid and Go to
page. The tag button SHALL open the tags used before as pills (on a false-mirror page: pressed for the page's own, a
press adding or removing it) and, in the false mirror, a field with Add. A false-mirror page of a PDF or a book SHALL
take drawing and no typing, as on the tablet. The false mirror's New notebook, New folder and Import SHALL be in a
menu at the top right of its screen.

#### Scenario: A book page in the false mirror
- **WHEN** the user opens a page of a book in the false mirror
- **THEN** the bar shows the pens, the eraser and layers, no text tool, and the user can draw on the page

### Requirement: The viewer is the tablet's screen
The viewer SHALL hold a port the Paper Pro's screen's shape (3:4), as large as the window allows by its height or its
width, within the window at every UI zoom, and SHALL be no taller than the port with its title and bar, and as wide as
its bar needs (the window allowing), so the bar never scrolls.

#### Scenario: A tall window
- **WHEN** the window is taller than it is wide
- **THEN** the port is as wide as the window allows and the viewer is only as tall as the port and its bar

### Requirement: Start waits for a lineup that could take a page
Start and Pause SHALL sit in the rail's foot, left of the version, on every screen (the Daemon screen holds none). Start SHALL show as Paused and be disabled while no lineup could take a page (none has a tag, or its
text model has no location, or a model on this computer has no start script), its hover saying so; passing the lineup's
test SHALL NOT be needed.

#### Scenario: No tags
- **WHEN** no lineup has a tag
- **THEN** the button reads Paused, cannot be pressed, and its hover says no lineup is ready
