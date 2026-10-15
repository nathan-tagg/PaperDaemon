# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: A text harness defines the job's protocols
**Reason**: Harnesses are data, and one host runs every job the same way. An intake, an output or a task
protocol in code would be an executor per model.
**Migration**: What a protocol could set becomes data: vision, the brief additions, the decision
settings, the features a harness switches off, and keyword assists ("A harness is data").

### Requirement: validate() sets how far a harness trusts its model
**Reason**: The host's validity rules are the same for every harness (jobs/decisions).
**Migration**: A harness that should trust its model less switches features off or adds assists ("A
harness may narrow what is offered, never loosen validity").
