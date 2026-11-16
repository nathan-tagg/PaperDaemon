## ADDED Requirements

### Requirement: The Mirror's library is changed as the False Mirror's is
With Mirror editing on, the Mirror's library screen SHALL offer what the False Mirror's offers: the + menu (Quick
sheets, New notebook, New folder, Import), files dropped on the screen imported into the folder open, and a long
press or a right-click selecting a notebook or folder for the selection's actions. Each change SHALL reach the tablet
through reMarkable's cloud as PaperDaemon's page edits do: a new item pushed, and an item already on the tablet
checked against the cloud before it is changed, never written over a change the tablet made since it was read, and
backed up before PaperDaemon first changes it; a book SHALL be filed as the desktop app files one, for the tablet to
lay out. A change SHALL be made in the Mirror at once and sent to the tablet in the background, one at a time in the order made (11-16: Create stayed gray while a send took 5 s); the screen SHALL say while changes are being sent, and SHALL say in plain words, by name, a change that could not reach the tablet. With Mirror editing off the Mirror's
library SHALL offer none of them.

In either library, while anything is selected a plain click on a notebook or folder SHALL open it and let the
selection go; Ctrl or Shift and a click, a right-click or a long press SHALL add one to the selection or take it away.

#### Scenario: A new notebook from the Mirror
- **WHEN** the user, with Mirror editing on, chooses New notebook from the Mirror's + menu
- **THEN** the notebook is made in the folder open and is on the tablet once it is pushed

#### Scenario: A right-click selects in the Mirror
- **WHEN** the user, with Mirror editing on, right-clicks a notebook in the Mirror
- **THEN** it is selected and the selection's actions show, as in the False Mirror

#### Scenario: A left click after a right-click opens
- **WHEN** the user right-clicks a notebook, then left-clicks it
- **THEN** the notebook opens and nothing stays selected

#### Scenario: Editing off
- **WHEN** Mirror editing is off
- **THEN** the Mirror's library shows no + menu, and a right-click or a long press selects nothing
