# Spec Delta

## Purpose

Gives each notebook a memory of past jobs, so a conversation can carry on from page to page, shows
that memory in the app, and lets the user empty it with one command.

## ADDED Requirements

### Requirement: Each notebook has a notepad
The host SHALL keep one notepad per notebook in PaperDaemon's data folder. Every job SHALL read the
notepad's recent entries into the model's context and SHALL add an entry saying what was asked and
what the job did.

#### Scenario: A follow-up on the next page
- **WHEN** a job answered "plan a three-day trip to Moab" on one page and the user writes "make day two
  shorter" on the next
- **THEN** the second job sees the first job's entry and knows what "day two" means

### Requirement: A skipped job writes nothing
A job that skips its page SHALL write no entry to the notepad. A skip changed nothing, and its note is only
the model's reasoning at the time.

#### Scenario: A page skipped
- **WHEN** a job skips a page, noting "nothing here asks for work"
- **THEN** the notebook's notepad is unchanged

### Requirement: Entries are filed by page, not by page number
Each entry SHALL be filed under the page's identity, never its number. When entries are shown to the
model, the host SHALL label each with that page's current number, as this page, or as a page no longer
in the notebook.

#### Scenario: A page moved
- **WHEN** the user moves a page from third to first after a job on it
- **THEN** the next job's notepad labels that entry as page 1

### Requirement: A wiped notepad is gone
Emptying a notepad SHALL delete its contents with no copy kept.

#### Scenario: After a wipe
- **WHEN** a notepad has been wiped
- **THEN** no file in PaperDaemon's data folder holds its old entries

### Requirement: The notepads are shown in the app
The app SHALL have a notepad screen that lists every notebook with a notepad, with its number of
entries and when the last was written. Notebooks in the trash SHALL NOT be listed. For the notebook the
user picks, the screen SHALL show the entries newest first. Each entry SHALL show:
- when it was written
- its page, by its current number, or as a page no longer in the notebook
- what was asked, and what the job did

New entries SHALL appear as jobs finish, without a reload.

#### Scenario: Reading a notebook's notepad
- **WHEN** the user opens the notepad screen and picks a notebook
- **THEN** its entries are listed newest first, each with its time, its page's current number, what
  was asked and what was done

#### Scenario: A job finishes while the screen is open
- **WHEN** a job in the shown notebook finishes
- **THEN** its entry appears at the top of the list without a reload

### Requirement: The screen shows what the next job is shown
The notepad screen SHALL show, word for word, the recent entries the next job in the chosen notebook
would be shown.

#### Scenario: Reading what the model reads
- **WHEN** the user opens a notebook's notepad on the screen
- **THEN** the text shown is exactly the text the next job in that notebook is shown

### Requirement: A notepad can be wiped from the app
The notepad screen SHALL let the user wipe the chosen notebook's notepad after a confirmation that
says how many entries go. This is the only way a notepad is emptied: nothing written on a page empties it.

#### Scenario: Wiping from the screen
- **WHEN** the user wipes the Garden plans notepad and confirms
- **THEN** its entries are gone with no copy kept, and the next job in that notebook sees an empty
  notepad
