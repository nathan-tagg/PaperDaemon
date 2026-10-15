# Spec Delta

## Purpose

When the tablet and a job change the same page, the user's writing must never be lost, and what the job meant
to do must not be dropped silently.

## ADDED Requirements

### Requirement: A push sends only what PaperDaemon changed
A push SHALL upload only the files PaperDaemon changed since the last pull. A file the tablet changed since then
SHALL NOT be uploaded, and the document SHALL NOT be marked as pulled, so the next pull brings the tablet's copy.

#### Scenario: The user wrote on another page meanwhile
- **WHEN** a job answered page 2 while the user wrote on page 1 of the same notebook
- **THEN** the push uploads page 2 only, and the next pull brings the user's page 1

### Requirement: The tablet's copy wins, and ours is kept
When the tablet and a job both changed one page, the pull SHALL keep the tablet's copy and SHALL set the job's
copy aside in the conflicts folder.

#### Scenario: Both changed one page
- **WHEN** the user wrote on page 3 while a job was answering page 3
- **THEN** page 3 is the user's, and the job's page 3 is in the conflicts folder

### Requirement: A conflict is resolved as a job
A conflict SHALL become a CONFLICT job queued behind the other jobs. Its turn SHALL carry both pages (the
user's and the job's) and the job that made the job's page, and the jobs it returns SHALL run on the user's
page; the job's copy SHALL never be written back over the user's. A page SHALL have at most one CONFLICT job
queued: a newer conflict on the same page replaces it.

#### Scenario: The user keeps writing
- **WHEN** a CONFLICT job for page 3 is queued and the user writes on page 3 again before it runs
- **THEN** one CONFLICT job for page 3 is queued, carrying the newest pages
