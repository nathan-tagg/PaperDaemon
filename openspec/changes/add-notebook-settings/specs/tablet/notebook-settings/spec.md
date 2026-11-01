## ADDED Requirements

### Requirement: A document's settings
The open document's title in the viewer SHALL open its sheet, in both mirrors, for notebooks, PDFs and books alike: its
name, to rename it; its tags; its cover, "Last page visited" or "First page", the document's own setting ticked; and
Export, the whole document. Saved, the cover SHALL show the page the setting names, drawn again for it. In the library,
the bar shown for the documents picked (a long or right click) SHALL offer their cover as a chevroned select.

#### Scenario: Renaming from the title
- **WHEN** the user clicks the open notebook's title, types a new name and saves
- **THEN** the notebook carries the new name in the viewer and in the library

#### Scenario: The cover from the library
- **WHEN** the user picks two notebooks in the library and chooses First page in the bar's cover select
- **THEN** both covers show their first pages

#### Scenario: Choosing the first page
- **WHEN** the user opens a notebook whose cover is the last page visited, chooses First page in its settings and saves
- **THEN** the notebook's cover shows its first page

### Requirement: The Mirror's setting is written as a page is
In the False Mirror the settings SHALL be written into the document's own files at once. In the Mirror the cover and the
name SHALL be written as the tablet stores them (the document's `coverPageNumber`: 0 for the first page, -1 for the last
visited; its .metadata's `visibleName`), every
other part of the document left as it is, and sent to the tablet, with a page's safety: only while Edit the Mirror is
on; never when the tablet changed the document's settings since PaperDaemon pulled them (the user is told, and nothing
is written); the document backed up before PaperDaemon first writes it. With Edit the Mirror off, the settings SHALL
show the document's setting, its choices disabled, with no note.

#### Scenario: Edit the Mirror off
- **WHEN** the user opens a Mirror notebook's settings with Edit the Mirror off
- **THEN** its cover setting shows and cannot be changed

#### Scenario: The tablet changed the document first
- **WHEN** the user saves a Mirror notebook's cover after the tablet changed that notebook and before PaperDaemon
  pulled the change
- **THEN** nothing is written, and the settings say the tablet changed the notebook first
