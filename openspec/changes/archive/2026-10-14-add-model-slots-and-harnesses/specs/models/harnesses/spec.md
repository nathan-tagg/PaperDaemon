# Spec Delta

## Purpose

Captures what differs between models in one harness per model family: its capabilities and parameters
(whether it can see a page, whether a tool call can be forced, how many steps a picture needs), and
the protocols a job runs by (what the model is shown, what it hands back, who does each task, and what
is refused). The host itself never forks per model, and any model still runs on the base harness.

## ADDED Requirements

### Requirement: A base harness runs any model
PaperDaemon SHALL have a base harness for each slot, built into the app, that runs a model no other harness
knows: for text, every ability PaperDaemon has, for a model that sees the page and can be made to call a
tool (the model test and the slot's capability overrides correct what the model cannot do); for pictures,
the step count, guidance and size most image servers accept.

#### Scenario: An unknown text model
- **WHEN** the text slot names a model that matches no harness
- **THEN** the base text harness is used, and the models screen shows its capabilities as guesses

### Requirement: A text harness defines the job's protocols
A text harness SHALL define four things, and the host SHALL run every job by them:
- the **intake protocol:** what the model is shown and told. It chooses from the host's readings of
  the page (its image, its typed text, the handwriting reader's lines with positions, its pictures and
  marks, the notebook's notepad and system prompt, the date and the user's location) and presents them
  the way that model works best, with the model's instructions and the tasks it is offered;
- the **output protocol:** what the model hands back, and what the host gets from it: tasks to carry
  out, a finished working copy of the page with a list of what it erased, a request for another turn,
  or a skip with its reason;
- the **job protocols**, one per job kind, held by the host (rebuild-harness-interface): whether the model
  supplies something, what the host does, and whether the result goes back to the model. A harness MAY
  override one;
- **validate():** the checks a result must pass before the host commits it.

A harness that leaves one of these out SHALL use the base harness's. The notebook's system prompt SHALL
reach the model word for word through every harness's intake.

#### Scenario: A model that cannot see
- **WHEN** a harness for a model without vision builds a job's intake
- **THEN** the model receives the typed text and the reader's lines with their positions, and no image

#### Scenario: The notebook's own instructions
- **WHEN** a notebook has a system prompt page and a job runs in it
- **THEN** the model receives that prompt word for word, whichever harness the slot uses

#### Scenario: The host does what the protocol leaves to it
- **WHEN** the Qwen 3.6 27B harness's chart protocol has the model supply the data and leaves placing
  and drawing to the host, and its model asks for a bar chart
- **THEN** the host places the chart and draws it from the model's data

#### Scenario: A model that draws for itself
- **WHEN** a harness's chart protocol leaves the drawing to its model
- **THEN** the host draws no chart, and checks the page the harness hands back with that harness's
  validate()

### Requirement: validate() sets how far a harness trusts its model
Each text harness's validate() SHALL decide what in a job's result is refused before the host commits
it. The base harness's validate() SHALL refuse:
- a planned place that received no content, sent back once so the model can fill it
- anything that depends on a failed step
- a deletion of the user's content beyond the request the job reports carrying out
- a new notebook
- a tag the user did not name

A harness MAY replace validate() to trust its model more or less.

#### Scenario: The base checks
- **WHEN** a job on the base harness hands back a page with a paragraph of the user's notes removed
  that it did not report as the request
- **THEN** validate() refuses it, and the page stays as it was

#### Scenario: A stricter harness
- **WHEN** a harness's validate() refuses every erasure, and its model asks to erase the request it
  carried out
- **THEN** the erasure is refused, and the rest of the job is committed

### Requirement: Harnesses can be added by the user
PaperDaemon SHALL load the harnesses it ships and any harness file the user puts in the `harnesses` folder of
PaperDaemon's data folder. Every harness that satisfies the harness interface SHALL appear in the harness
dropdowns under the name it declares. A file that fails to load or does not satisfy the interface
SHALL be listed with the reason, and SHALL NOT stop PaperDaemon or the other harnesses.

#### Scenario: A harness for a new model
- **WHEN** the user adds a harness file for a model family PaperDaemon does not ship and PaperDaemon starts
- **THEN** the harness appears in the text slot's dropdown under its declared name

#### Scenario: A broken harness file
- **WHEN** a harness file in the folder has an error
- **THEN** the models screen lists that file with its error, and every other harness still works

### Requirement: Shipped harnesses
PaperDaemon SHALL ship harnesses for Qwen 3.6 27B (text), Qwen 3.8 27B (text), FLUX.2 Klein 9B (image)
and Z-Image Turbo (image). Each harness SHALL state the capabilities and parameters it sets. No lineup SHALL
ship: the user makes their own (the maintainer's decision).

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
seed the user wrote explicitly SHALL be used as written. A step count counts as the user's when that
number appears in the notebook's system prompt or on the page.

#### Scenario: The model asks for too many steps
- **WHEN** the model asks Klein for 30 steps on its own
- **THEN** the picture is made with 12 steps, the top of Klein's range

#### Scenario: The user asks for 36 steps and seed 8080
- **WHEN** the user's page asks for a picture with 36 steps and seed 8080
- **THEN** the picture is made with 36 steps and seed 8080
