## ADDED Requirements

### Requirement: A text model's harness is set by its strength
PaperDaemon SHALL ship three text harness bases, Weak, Medium and Strong, and the Text / Reasoning tab SHALL set a
lineup's text harness with a slider over them, showing the picked base's description under it. Strong SHALL be the
lean way of working; Medium SHALL be built for Qwen 3 models running in llama.cpp and say so; Weak SHALL be Medium
with short answers and with sketches, social posts, pictures from the web and the long games turned off. A harness
file of the user's own SHALL be offered under Your harness when there is one, and picking it SHALL replace the
slider's base until None is picked.

#### Scenario: Moving the slider
- **WHEN** the user moves a lineup's Harness slider from Strong to Weak
- **THEN** the lineup runs on the Weak base, the description under the slider is Weak's, and the capability boxes
  show Weak's own values

### Requirement: What the text model can do on its own
A text harness SHALL say whether its model can search the web and make images on its own, and the Text / Reasoning
tab SHALL show these with Vision as checkboxes the user may change, with a line naming what the model can do and a
warning that claiming a capability the model lacks causes failed or wrong jobs. A lineup's own search SHALL be used
whenever it has one. With no search of its own, a model that can search SHALL be told to look facts up with its own
search, and PaperDaemon SHALL turn that search on where the program's data or the API says how; a model that cannot
SHALL be told facts cannot be looked up. Image generation SHALL be shown and SHALL NOT be offered to the user until
PaperDaemon can take a picture from a text model's answer. The Image and Network tabs SHALL say that what they set is
used instead of the text model's own.

#### Scenario: Claude with no search in its lineup
- **WHEN** a lineup on the `claude` program, on Strong, has no search on its Network tab
- **THEN** the program is run with its own web search allowed, and the model is told to look facts up with it

#### Scenario: A lineup with its own search
- **WHEN** a lineup whose model can search has a search on its Network tab
- **THEN** PaperDaemon's search step is used and the model's own search is not turned on

#### Scenario: Neither
- **WHEN** a lineup has no search and its model cannot search
- **THEN** the model is told facts cannot be looked up, to say so, and never to fill them in from memory
