# models/harnesses Specification

## Purpose
Captures what differs between models in one harness per model family: its capabilities and parameters
(whether it can see a page, whether a tool call can be forced, how many steps a picture needs), and
the protocols a job runs by (what the model is shown, what it hands back, who does each task, and what
is refused). The host itself never forks per model, and any model still runs on the base harness.

## Requirements

### Requirement: A base harness runs any model
PaperDaemon SHALL have a base harness for each slot, built into the app, that runs a model no other harness
knows: for text, every ability PaperDaemon has, for a model that sees the page and can be made to call a
tool (the model test and the slot's capability overrides correct what the model cannot do); for pictures,
the step count, guidance and size most image servers accept.

#### Scenario: An unknown text model
- **WHEN** the text slot names a model that matches no harness
- **THEN** the base text harness is used, and the models screen shows its capabilities as guesses

### Requirement: Harnesses can be added by the user
PaperDaemon SHALL load the harnesses it ships and every harness file the user puts in the `harnesses`
folder of PaperDaemon's data folder, in the same format and by the same rules. Every harness that loads
SHALL appear in the harness dropdowns under the name it declares. A file that fails to load or breaks a
rule SHALL be listed with the reason, and SHALL NOT stop PaperDaemon or the other harnesses.

#### Scenario: A harness for a new model
- **WHEN** the user adds a harness file for a model family PaperDaemon does not ship and PaperDaemon starts
- **THEN** the harness appears in the text slot's dropdown under its declared name

#### Scenario: A broken harness file
- **WHEN** a harness file in the folder has an error
- **THEN** the models screen lists that file with its error, and every other harness still works

### Requirement: Shipped harnesses
PaperDaemon SHALL ship, as data files, harnesses for Qwen 3.6 27B (text), Qwen 3.8 27B (text), FLUX.2
Klein 9B (image) and Z-Image Turbo (image), beside the default text and image harnesses. Each harness
SHALL state the capabilities and parameters it sets. The shipped lineups SHALL be "Qwen 3.8 + Klein", the
default, and "Qwen 3.6 + Klein".

#### Scenario: Klein's steps
- **WHEN** the image slot uses the FLUX.2 Klein 9B harness
- **THEN** a picture defaults to 4 steps, the model may choose from 4 to 12, and a coloring page uses 12

#### Scenario: A quantized Qwen 3.8 file
- **WHEN** the start script names a Qwen 3.8 27B file in some quantization
- **THEN** the Qwen 3.8 27B harness is guessed

### Requirement: An image harness owns its workflows
An image harness SHALL carry its WORKFLOWS: named recipes, each a prompt template with the place for the
picture's subject, plus the settings it needs (such as its step count), optionally LoRA adapters, and
whether it starts from a reference picture. A workflow's name SHALL mean the same request on every image
harness, and each harness SHALL carry it out its own way. The coloring page SHALL be the workflow
`childrensColoringBook`, its wording and its steps held by the image harness alone, word for word as the
coloring prompt was. The host SHALL ask for a picture by workflow name and send only the subject; the
engine SHALL apply the active image harness's wording and settings. A workflow SHALL be optional: a
picture asked for without one SHALL go to the image model exactly as the text model wrote it. A workflow
the active image harness does not have SHALL NOT fail the job: the subject SHALL go as a plain prompt and
the job's log SHALL say the workflow was missing.

#### Scenario: A coloring page on Klein
- **WHEN** a job asks for a coloring page of an owl and the image slot uses the FLUX.2 Klein 9B harness
- **THEN** the picture is made with Klein's coloring book wording around "an owl" and 12 steps

#### Scenario: A plain picture
- **WHEN** a job asks for a picture with no workflow
- **THEN** the image model receives the text model's description exactly as written

#### Scenario: A workflow the image model lacks
- **WHEN** a job asks for a workflow and the lineup's image harness has none of that name
- **THEN** the picture is made from the plain subject, and the job's log names the missing workflow

### Requirement: An image harness says what its model can do, and the text model is told
An image harness SHALL state its model's abilities (making a picture from a sentence, editing a picture
handed to it as a reference, redrawing from another picture, changing a masked part). The text harness's
brief SHALL tell the model the active image harness's abilities and its workflows, each with its one-line
description. An edit the image harness cannot do SHALL NOT be sent to the server; a game that would edit
its scene from a reference SHALL draw it afresh instead.

#### Scenario: Z-Image and a game's scene
- **WHEN** a game wants its scene edited from the previous picture and the image slot uses Z-Image Turbo
- **THEN** the scene is drawn afresh, and the job's log says the image model has no reference editing

### Requirement: A workflow may apply LoRA adapters
A workflow MAY name LoRA files with a strength each. They SHALL be sent with that workflow's pictures
only, in the image server's own per-request list, and the model files SHALL never be changed. A file the
server does not list SHALL be left out, the picture SHALL be made without it, and the job's log SHALL name
the missing file. PaperDaemon SHALL ship no LoRA and no shipped workflow SHALL name one; an example user
harness that adds a workflow with a LoRA SHALL ship, inactive, with the code.

#### Scenario: A LoRA that is not there
- **WHEN** a workflow names `ink-wash.safetensors` and the image server's LoRA folder has no such file
- **THEN** the picture is made without it, and the job's log says the file was missing

### Requirement: PaperDaemon guesses the harness and says why
When the slot's harness is set to automatic, PaperDaemon SHALL pick the harness whose model family matches
the slot's model name, the model the server reports, or the model file named in the launch script, in
that order, and fall back to the base harness. The models screen SHALL show the guess and what it was
based on.

#### Scenario: A quantized file
- **WHEN** the launch script names `qwen3.6-27b-Q8_0.gguf` and the harness is automatic
- **THEN** the Qwen 3.6 27B harness is picked, and the screen says it was guessed from the launch script

#### Scenario: Nothing matches
- **WHEN** no hint matches any harness
- **THEN** the base harness is used and the screen says no harness matched

### Requirement: The user can pick the harness
The user SHALL be able to set each slot's harness to automatic, the base harness, or any harness of
that slot's kind, shipped or the user's own, and the user's pick SHALL win over any guess.

#### Scenario: Overriding the guess
- **WHEN** PaperDaemon guessed the base harness and the user picks Z-Image Turbo
- **THEN** jobs use the Z-Image Turbo harness until the user changes it

### Requirement: Variants that change parameters are told apart
Variants that keep a model's parameterization, such as another quantization,
SHALL select the same harness. A variant that needs different parameters SHALL NOT be guessed as the
harness of the variant it differs from.

#### Scenario: Klein base is not Klein
- **WHEN** the model file is the undistilled FLUX.2 Klein base model
- **THEN** the FLUX.2 Klein 9B harness, which assumes the 4-step distilled model, is not guessed

### Requirement: Capability overrides per slot
The user SHALL be able to override each capability a harness sets for one slot. The models screen SHALL
show each capability's effective value and where it came from: the harness, the user's override, or a
test result the user accepted.

#### Scenario: A server started without its vision projector
- **WHEN** the Qwen 3.6 27B server runs without its vision projector and the user turns vision off
- **THEN** jobs on that slot send no page images, and the screen shows vision off by the user's override

### Requirement: No images to a model that cannot see
PaperDaemon SHALL NOT send an image to a text model whose effective vision capability is off. The one
exception is the model test's single synthetic image, which exists to check whether the model can see.

#### Scenario: A text-only model
- **WHEN** a job runs on a text slot with vision off
- **THEN** no request to that slot contains image content

#### Scenario: Testing whether a model can see
- **WHEN** the user tests a text slot with vision off
- **THEN** the test sends one small synthetic picture and no page of the user's

### Requirement: Picture parameters come from the harness, the user's words win
Picture requests SHALL take their steps, guidance, sampler, scheduler and size from the image harness.
When the model chooses the steps itself, the choice SHALL stay inside the harness's range. Steps and a
seed the user wrote explicitly SHALL be used as written. A step count or a seed counts as the user's when
the model quotes the user's words that name it, and the host finds the quote in the notebook's system
prompt or on the page.

#### Scenario: The model asks for too many steps
- **WHEN** the model asks Klein for 30 steps on its own
- **THEN** the picture is made with 12 steps, the top of Klein's range

#### Scenario: The user asks for 36 steps and seed 8080
- **WHEN** the user's page asks for a picture with 36 steps and seed 8080, and the model quotes those words
- **THEN** the picture is made with 36 steps and seed 8080

#### Scenario: A number the user never wrote
- **WHEN** the model asks for 40 steps and quotes words that are not in the prompt or on the page
- **THEN** the picture is made with 12 steps, the top of Klein's range

### Requirement: A harness is data
A harness SHALL be data, in one format for shipped and user harnesses:
- its identity, and the patterns that pick it and refuse it;
- the harness it extends;
- its capabilities and parameters;
- request fields keyed by a capability's value;
- its brief additions and decision settings;
- the features it switches off, and its keyword assists;
- for an image harness, its abilities and workflows.

A harness SHALL carry no code, and the engine and the host SHALL run every harness the same way. A field a
harness leaves out SHALL take the value of the harness it extends. The notebook's system prompt SHALL
reach the model word for word whatever the harness.

#### Scenario: A thinking switch as data
- **WHEN** a text harness says that requests carry `chat_template_kwargs.enable_thinking: false` while
  thinking is off, and the slot's thinking is off
- **THEN** every chat request to that slot carries that field

#### Scenario: A model that cannot see
- **WHEN** a job runs on a harness whose model has no vision
- **THEN** the model receives the typed text and the reader's lines with their positions, and no image

#### Scenario: The notebook's own instructions
- **WHEN** a notebook has a system prompt page and a job runs in it
- **THEN** the model receives that prompt word for word, whichever harness the slot uses

### Requirement: A harness may narrow what is offered, never loosen validity
A harness's data MAY switch features off and MAY add keyword assists. It SHALL NOT change the host's
validity rules.

#### Scenario: A harness without erasing
- **WHEN** a harness switches the erase feature off, and its model finishes a request
- **THEN** the model is offered no erasing, and the request stays on the page

### Requirement: A harness may carry keyword assists
A text harness MAY carry keyword assists. Each SHALL name one decision that an enabled feature declares,
the text it reads, its keywords, an optional condition on the model's value, and either a hint or the
value it sets. A harness file whose assist names an unknown decision or breaks the format SHALL be listed
with the reason and SHALL NOT load. No shipped harness SHALL carry assists; an inactive example SHALL
ship with the code.

#### Scenario: An assist for an unknown decision
- **WHEN** a user harness carries an assist for a decision no feature declares
- **THEN** the models screen lists that file with the reason, and every other harness still loads
