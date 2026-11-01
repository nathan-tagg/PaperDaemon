## ADDED Requirements

### Requirement: A document's settings
The viewer's title bar SHALL have a settings button for the open document, in both mirrors, for notebooks, PDFs and
books alike. It SHALL open the document's settings: its cover, "Last page visited" or "First page", the document's own
setting ticked. Saved, the cover SHALL show the page the setting names, drawn again for it.

#### Scenario: Choosing the first page
- **WHEN** the user opens a notebook whose cover is the last page visited, chooses First page in its settings and saves
- **THEN** the notebook's cover shows its first page

### Requirement: The Mirror's setting is written as a page is
In the False Mirror the setting SHALL be written into the document's own files at once. In the Mirror it SHALL be
written as the tablet stores it (the document's `coverPageNumber`: 0 for the first page, -1 for the last visited), every
other part of the document left as it is, and sent to the tablet, with a page's safety: only while Edit the Mirror is
on; never when the tablet changed the document's settings since PaperDaemon pulled them (the user is told, and nothing
is written); the document backed up before PaperDaemon first writes it. With Edit the Mirror off, the settings SHALL
show the document's setting and say that Edit the Mirror, in Settings, changes it.

#### Scenario: Edit the Mirror off
- **WHEN** the user opens a Mirror notebook's settings with Edit the Mirror off
- **THEN** its cover setting shows, cannot be changed, and the settings say Edit the Mirror, in Settings, changes it

#### Scenario: The tablet changed the document first
- **WHEN** the user saves a Mirror notebook's cover after the tablet changed that notebook and before PaperDaemon
  pulled the change
- **THEN** nothing is written, and the settings say the tablet changed the notebook first
