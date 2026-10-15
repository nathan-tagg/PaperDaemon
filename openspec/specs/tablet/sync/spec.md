# tablet/sync Specification

## Purpose
Keeps PaperDaemon's own copy of the user's reMarkable library current, learns of changes as they happen,
and writes back to the cloud without ever losing the user's work.

## Requirements

### Requirement: PaperDaemon keeps its own mirror
PaperDaemon SHALL keep its own copy of the library in its data folder, and SHALL NOT read or write the
copy of any other reMarkable tool on the machine.

#### Scenario: The desktop app is installed too
- **WHEN** the reMarkable desktop app is installed and syncing on the same machine
- **THEN** PaperDaemon neither reads nor writes the desktop app's cache

### Requirement: Pulls are incremental and verified
The first pull SHALL copy the whole library. Later pulls SHALL download only files whose content
changed, SHALL check every download against the hash the cloud advertised, and SHALL report progress
as files and bytes.

#### Scenario: Nothing changed
- **WHEN** the user pulls and the library's root has not changed since the last pull
- **THEN** nothing is downloaded and the answer says the mirror is up to date

#### Scenario: A corrupt download
- **WHEN** a downloaded file does not match its advertised hash
- **THEN** the pull fails with an error naming the file, and no partial file appears in the mirror

### Requirement: The mirror holds what a job needs
Pulls SHALL bring each document's metadata, content listing, pages and page data, the pictures placed
on pages, and PDF and EPUB sources. Thumbnails are not needed.

#### Scenario: A page with a picture on it
- **WHEN** a pulled page holds a picture the user placed with the tablet
- **THEN** the picture's file is in the mirror beside the page

### Requirement: Trash is gone
Everything in the reMarkable trash SHALL count as deleted for every part of PaperDaemon: it is never
listed, read, dispatched or written.

#### Scenario: A tagged notebook goes to the trash
- **WHEN** the user moves a tagged notebook to the trash and PaperDaemon pulls
- **THEN** no part of PaperDaemon treats that notebook or its pages as present

### Requirement: PaperDaemon learns of changes without polling
PaperDaemon SHALL hold the cloud's change-notification connection, report every change it is told about so
that a pull can follow, tell its own writes apart from other devices' changes, and reconnect after a
dropped connection, waiting longer between repeated failures.

#### Scenario: The tablet syncs a page
- **WHEN** the tablet uploads a change
- **THEN** PaperDaemon hears of it through the notification connection, without polling the cloud

#### Scenario: The connection drops
- **WHEN** the notification connection closes
- **THEN** PaperDaemon reconnects, and backs off further after each failure in a row

### Requirement: No permanent deletes
No PaperDaemon write SHALL remove a document from the cloud library. Moving a document to the trash SHALL
be the furthest any write goes.

#### Scenario: Writing a page
- **WHEN** PaperDaemon writes a page back to the cloud
- **THEN** every document that was in the library before the write is still in it after

### Requirement: A write never overwrites a newer library
A PaperDaemon write SHALL fail, and leave the cloud unchanged, when the library changed between PaperDaemon
reading it and writing it.

#### Scenario: The tablet synced in between
- **WHEN** the tablet syncs a change after PaperDaemon read the library and before PaperDaemon writes
- **THEN** PaperDaemon's write is refused, nothing is lost, and PaperDaemon can read again and retry

### Requirement: Pages PaperDaemon added survive the tablet's re-upload
When the tablet uploads a notebook's page list while pages PaperDaemon added have not reached the cloud
yet, the next pull SHALL keep those pages in the mirror and SHALL take the tablet's list as it is for
every other page.

#### Scenario: The user opens the notebook during a job
- **WHEN** PaperDaemon has added a page it has not pushed yet and the tablet re-uploads the notebook's
  page list
- **THEN** the pulled page list holds the tablet's pages in the tablet's order plus PaperDaemon's added page
