# drawing/documents Specification

## Purpose
Files results that do not fit on the page, such as a detailed calendar, as documents on the tablet next
to the user's inbox notebook, with a pointer on the page.

## Requirements

### Requirement: Documents go beside the inbox notebook
A document a job makes SHALL be created as a PDF in the folder that holds the inbox notebook named in
the settings (the top level when the inbox has no folder), and the job's page SHALL get one line naming
it.

#### Scenario: A detailed calendar
- **WHEN** a job files next month's calendar as a document
- **THEN** a PDF named for the month appears beside the inbox notebook, and the page gets one line
  pointing to it

### Requirement: Missing folders on the inbox's path are made
When a folder on the inbox's path does not exist, the first document SHALL create it, and nothing else
in the library SHALL change.

#### Scenario: First document
- **WHEN** a job files its first document and the inbox is set to "Projects/Coloring inbox" with no "Projects"
  folder yet
- **THEN** the "Projects" folder is created and the document placed in it

### Requirement: Pictures at full resolution go as documents only on request
A picture the user asked to get as a document SHALL be filed as a one-page PDF at the tablet's native
resolution; otherwise pictures go on the page.

#### Scenario: Asked for a printable picture
- **WHEN** a page asks for a map "as a document"
- **THEN** the map is filed as a one-page PDF beside the inbox notebook
