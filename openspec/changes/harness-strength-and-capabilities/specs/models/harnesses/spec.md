## ADDED Requirements

### Requirement: A text model's harness is set by its strength
PaperDaemon SHALL ship three text harness bases, Weak, Medium and Strong, and the Text / Reasoning tab SHALL set a
lineup's text harness with a dropdown of them, showing under it the picked base's description and the models it was
tested with. Strong SHALL be the lean way of working; Weak SHALL be Medium with short answers and with sketches,
social posts, pictures from the web and the long games turned off. The tab SHALL offer no other harness and no way to
add one.

#### Scenario: Picking a base
- **WHEN** the user picks Weak in a lineup's Harness dropdown
- **THEN** the lineup runs on the Weak base, the description under the dropdown is Weak's, and the capability pills are
  Weak's own

### Requirement: What the text model can do on its own
A text harness SHALL say whether its model can search the web and make images on its own, and the Text / Reasoning
tab SHALL show these with Vision as pills under a type-ahead box the user adds them with; hovering a pill SHALL say
that it only tells PaperDaemon what the model can do and that the Image or Network tab is used instead when set. The
help modal SHALL end in a warning card: claiming a capability the model lacks causes failed or wrong jobs. A lineup's
own search SHALL be used whenever it has one. With no search of its own, a model that can search SHALL be told to look
facts up with its own search, and PaperDaemon SHALL turn that search on where the program's data or the API says how;
a model that cannot SHALL be told facts cannot be looked up. With no image model of its own, a lineup whose text model
makes images SHALL have its pictures made by the text model's server and taken from its reply. The Image and Network
tabs SHALL say that what they set is used instead of the text model's own.

#### Scenario: Claude with no search in its lineup
- **WHEN** a lineup on the `claude` program, on Strong, has no search on its Network tab
- **THEN** the program is run with its own web search allowed, and the model is told to look facts up with it

#### Scenario: A lineup with its own search
- **WHEN** a lineup whose model can search has a search on its Network tab
- **THEN** PaperDaemon's search step is used and the model's own search is not turned on

#### Scenario: Neither
- **WHEN** a lineup has no search and its model cannot search
- **THEN** the model is told facts cannot be looked up, to say so, and never to fill them in from memory

#### Scenario: A server that makes its own pictures
- **WHEN** a lineup's Image tab has no model and its text model has the Image generation capability
- **THEN** an image step asks the text model's server for the picture and puts the picture from its reply on the page
