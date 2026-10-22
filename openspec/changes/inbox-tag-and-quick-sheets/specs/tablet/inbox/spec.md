# Spec Delta

## ADDED Requirements

### Requirement: The inbox is a tag
Send to Tablet SHALL add its page to every live notebook carrying the inbox tag (Settings: tags.inbox), in the
Mirror (with an account signed in) and in the False Mirror. A library with no such notebook SHALL take the page at
the end of its Quick sheets. A notebook with the inbox tag SHALL never be worked on.

#### Scenario: Two tagged notebooks
- **WHEN** two notebooks carry the inbox tag and a picture is sent
- **THEN** each gets a new page with it, and neither page starts a job

#### Scenario: No tagged notebook
- **WHEN** no notebook carries the inbox tag and the library has a Quick sheets at its root
- **THEN** the page is added at the end of the Quick sheets

### Requirement: Send says it sent
After a send the button SHALL read "Sent to all inboxes" until the window is loaded again, with no page number.

#### Scenario: A decomp sent
- **WHEN** the user sends a decomp
- **THEN** its button reads "Sent to all inboxes"

### Requirement: Quick sheets in the False Mirror
The False Mirror's + menu SHALL offer Quick sheets, which opens the library's Quick sheets on a new page at its end
without asking for a name, making one at the root when there is none.

#### Scenario: No Quick sheets yet
- **WHEN** the user picks Quick sheets in a False Mirror with none
- **THEN** a notebook named Quick sheets is made at the root and opens on its first page

### Requirement: A new notebook takes the tablet's options
New notebook in the False Mirror SHALL ask for its name, its cover (the page last visited or the first page) and,
with an account signed in, its template.

#### Scenario: Without an account
- **WHEN** no account is signed in
- **THEN** the dialog shows no templates and the notebook's page is blank

### Requirement: The player answers by typing or writing
A game page's picture SHALL end where the player's space begins, so typed text lands in the space. A turn SHALL
read the player's typed text and their handwriting there.

#### Scenario: A typed reply
- **WHEN** the player types their message under a chat page's picture
- **THEN** it is read exactly as their message and taken off the page
