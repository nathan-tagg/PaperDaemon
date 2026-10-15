# Spec Delta

## Purpose

Decides which pages of the user's library need a job and when, dispatches those jobs one at a time,
and leaves every other page alone.

## ADDED Requirements

### Requirement: One daemon per account
Exactly one daemon SHALL dispatch jobs for a reMarkable account on a machine. A second PaperDaemon started
on the same data folder SHALL NOT start a second daemon.

#### Scenario: PaperDaemon started twice
- **WHEN** the user starts PaperDaemon while it is already running on the same data folder
- **THEN** the second start does not run a daemon, and says PaperDaemon is already running

### Requirement: The daemon wakes on change
The daemon SHALL pull the library when the cloud's change notifications report a change from another
device. While the notification connection is down, it SHALL check the library's root at a low rate
until the connection returns.

#### Scenario: The user tags a page
- **WHEN** the user adds the trigger tag to a page on the tablet and the tablet syncs
- **THEN** the daemon pulls and finds the page without the user doing anything in PaperDaemon

### Requirement: Tags inherit
A page SHALL count as tagged when the page, its notebook, or any folder above the notebook carries the
trigger tag.

#### Scenario: A tagged folder
- **WHEN** a folder carries the trigger tag and the user writes a request on a page of a notebook inside it
- **THEN** that page is dispatched as if the page itself were tagged

### Requirement: The ignore tag wins
A page SHALL NOT be dispatched when the page, its notebook, or any folder above it carries the tag
"ignore", at whatever level it was written and whatever other tags there are. The name is fixed and
universal, not a setting, and is matched ignoring case.

#### Scenario: An ignored page in a tagged notebook
- **WHEN** a notebook carries the trigger tag and one of its pages carries "Ignore"
- **THEN** that page is never dispatched, and the notebook's other pages are

#### Scenario: An ignored folder
- **WHEN** a folder carries "ignore" and a notebook inside it carries the trigger tag
- **THEN** no page of that notebook is dispatched

### Requirement: Old pages under a new tag are left alone
When a notebook or folder is tagged, its pages that were last changed before the tag was added SHALL be
recorded as baseline and SHALL NOT be dispatched. A baseline page SHALL be dispatched once the user
changes it.

#### Scenario: Tagging a full notebook
- **WHEN** the user tags a notebook that already holds forty written pages
- **THEN** none of the forty pages is dispatched, and a page the user writes on afterward is

### Requirement: A new ledger starts from what is already there
When the daemon starts with an empty ledger, as on PaperDaemon's first run or after the ledger was reset,
every tagged page it finds SHALL be recorded as baseline and SHALL NOT be dispatched, and the overview
SHALL say how many pages were recorded this way. Those pages SHALL be dispatched once the user changes
or retags them.

#### Scenario: Moving over from another assistant
- **WHEN** PaperDaemon starts for the first time on a library where two hundred tagged pages were already
  answered by another tool
- **THEN** none of them is dispatched, the overview says two hundred pages were recorded as they are,
  and a page the user writes on afterward is dispatched

### Requirement: A tagged page with nothing on it waits
A tagged page with no ink, typed text or picture SHALL wait and SHALL NOT be dispatched until content
arrives.

#### Scenario: The tag syncs before the ink
- **WHEN** a page's tag reaches the cloud before its ink does
- **THEN** the page waits, and is dispatched when the ink arrives

### Requirement: The ledger decides what comes back
The daemon SHALL record, for each page it dispatches, the outcome and a fingerprint of the page's
content (its ink, typed text and pictures, not its file bytes). A done or skipped page SHALL be
dispatched again only when its content changes (reopened) or when its trigger tag was removed and added
again (retagged).

#### Scenario: The user writes a follow-up
- **WHEN** the user adds a new line to a page PaperDaemon already answered
- **THEN** the page is dispatched again as reopened

#### Scenario: The user retags an unchanged page
- **WHEN** the user removes the trigger tag from an answered page and adds it back without other changes
- **THEN** the page is dispatched again as retagged

### Requirement: PaperDaemon's own writes never wake the daemon
The daemon SHALL record a page's fingerprint after the job's last write reached the cloud, so that
PaperDaemon's own changes to a page never make it reopened.

#### Scenario: After a job
- **WHEN** a job writes its answer on a page and pushes it
- **THEN** the daemon does not dispatch that page again because of the answer

### Requirement: An update never reopens the library
A new version of PaperDaemon SHALL compute the same fingerprint for every unchanged page as the version
before it.

#### Scenario: Updating PaperDaemon
- **WHEN** PaperDaemon is updated and restarted
- **THEN** no page whose content did not change is dispatched

### Requirement: Jobs start after a page settles, one at a time
The daemon SHALL start a job only after the page has stopped changing, and SHALL run one job at a time,
in the order pages became ready.

#### Scenario: The user is still writing
- **WHEN** the user keeps writing on a tagged page and the tablet syncs several times
- **THEN** no job starts until the page has stopped changing

### Requirement: System prompt pages and trash are never jobs
A page tagged `sprompt` holds its notebook's standing instructions and SHALL NOT be dispatched, whatever
other tags it carries, and a notebook whose only page is its system prompt page SHALL start no job.
`sprompt` counts only as a PAGE tag: on a notebook or a folder it means nothing, neither a trigger nor a
reason to leave anything alone. The name is fixed and universal, not a setting, and is matched ignoring
case. Nothing in the trash SHALL be dispatched.

#### Scenario: sprompt on a notebook
- **WHEN** a notebook carries "sprompt" and one of its pages carries the trigger tag
- **THEN** that page is dispatched like any other

#### Scenario: A new notebook with only instructions
- **WHEN** the user creates a tagged notebook whose one page is tagged `sprompt`
- **THEN** no job starts until the user writes on another page

### Requirement: The user can pause the daemon
The user SHALL be able to pause and resume the daemon from the UI. A paused daemon SHALL start no job
and SHALL catch up on resume.

#### Scenario: Pausing during a meeting
- **WHEN** the user pauses the daemon and tags two pages, then resumes
- **THEN** no job runs while paused, and both pages are dispatched after resuming

### Requirement: The overview shows what happened
The overview SHALL list, for each job, the notebook, the page number, the state that caused the job,
the job's phases and its outcome.

#### Scenario: A job finishes
- **WHEN** a job answers a reopened page
- **THEN** the overview shows the notebook, the page number, "reopened", the phases and "answered"
