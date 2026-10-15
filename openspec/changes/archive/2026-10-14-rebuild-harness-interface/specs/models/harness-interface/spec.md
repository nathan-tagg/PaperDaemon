# Spec Delta

## Purpose

The text harness as an interface the host calls, so that what differs between models (what they are shown,
how their replies read, how they are asked small questions) lives in the harness and never in the host.

## ADDED Requirements

### Requirement: A text harness implements the interface the host calls
A text harness SHALL implement:
- `intake`: from the page bundle, the offered job kinds and the image harness's offer, the first turn: the
  messages the model is shown and told, and the tools on offer;
- `output`: from the model's reply, exactly one of: jobs (from the enumerated kinds), a finished page with what
  it erased, another turn, lines asked back to the user, or a skip with its reason;
- the assist protocols `locate`, `read_ink` and `describe`: the turn that asks, and the reading of its reply;
- `validate`: the refusals and fixes applied to what is staged before commit;
- `conflict`: a turn from the user's page, the job's page and the job that made it, read back through `output`;
- `skill`: what the model is told about a job kind or tool, from prompt files the harness owns;
- `declare`: its needs (vision, forced tool calls, output size), the job kinds it supports, and abilities its
  model provides itself.

The host SHALL send every turn a harness builds to the text model and hand the raw reply back to the same
harness to read. The notebook's system prompt SHALL reach the model word for word through every intake.

#### Scenario: A reply the harness reads as jobs
- **WHEN** the model answers the first turn with a plan of a search and a chart
- **THEN** the harness's `output` returns two jobs, SEARCH and CHART, and the host runs them in that order

#### Scenario: A reply that asks to look closer
- **WHEN** the model answers by asking to look closer at part of the page
- **THEN** `output` returns another turn, the host serves the look, and sends the next turn the harness builds

### Requirement: The default harness is built into PaperDaemon
PaperDaemon's own text harness SHALL be part of the app, not a file in the harnesses folder. It SHALL carry
today's flow (the brief, the decision tool, one focused turn per job that needs the model, the host placing and
drawing), and for the same page and settings it SHALL produce the same prompts and tool schemas, byte for byte,
as the host did before this change. Every method a harness leaves out SHALL be the default's.

#### Scenario: No harness chosen
- **WHEN** a lineup's text slot names no harness and none is guessed
- **THEN** jobs run on the built-in default, and the harnesses folder holds no file named for it

#### Scenario: The move changes nothing
- **WHEN** the baseline pages are run through the built-in default
- **THEN** the system prompt, the tools and every turn's messages are byte-identical to the recorded baseline

### Requirement: A harness overrides only what it changes
A harness in the `llm` folder SHALL be either a Python file defining a subclass of the built-in default that
overrides some of its methods, or a folder of skill files that replaces some of the default's skills and
changes no code. The engine SHALL load both kinds at start. A file that fails to load SHALL be listed with its
reason and SHALL NOT stop PaperDaemon or the other harnesses.

#### Scenario: A skills-only harness
- **WHEN** the user adds a folder whose `skills/write.md` rewords what the model is told about writing
- **THEN** jobs on that harness tell the model the new wording for writing and everything else as the default

#### Scenario: A Python harness with an error
- **WHEN** a harness `.py` file raises an error when loaded
- **THEN** the harness list shows the file and the error, and the other harnesses load

### Requirement: Every harness file says its server, models and notes
Every harness file, text or image, SHALL state `server` (the server or API it is made for) and `models` (the
models it is made for), and MAY state `notes`. These are for people reading the file: PaperDaemon SHALL show
them and SHALL NOT act on them, and a harness SHALL NOT inherit them from the harness it extends. A harness
SHALL be named for its server and model, as "llama.cpp - Qwen 3.8 27B"; a model reached with an API key names
its API as the server, as "Anthropic API - Claude Opus 5.5". A file missing `server` or `models` SHALL be
listed as broken with what to add.

#### Scenario: A harness without a server
- **WHEN** a harness file in the folder has no `server`
- **THEN** it is listed as broken with "say which server it is made for", and does not load

### Requirement: Each kind of harness has its folder and its guide
The harnesses folder SHALL hold an `llm` folder and an `image` folder, each with a "How to create a new
harness.md" written for that kind. "+ Add a harness" SHALL open the folder of the tab's kind.

#### Scenario: Adding an image harness
- **WHEN** the user presses "+ Add a harness" on the Image tab
- **THEN** File Explorer opens the `image` folder, with the image harness guide in it

### Requirement: validate() keeps the page inside its limits
Before every commit the host SHALL run the harness's `validate()`. The default SHALL check that nothing staged
lies outside the safe area, and that the page holds no more strokes than its limit (250,000). Over the limit the
host SHALL fix the page rather than refuse it: written text continues on a new page right after this one, and a
picture is decomposed again with a lower region budget. A harness MAY add checks and SHALL NOT remove these.

#### Scenario: A long answer
- **WHEN** a job's answer would take the page past the stroke limit
- **THEN** the rest of the answer goes on a new page right after this one, and the commit goes through

#### Scenario: Ink under the toolbar
- **WHEN** a job stages ink inside the top safe zone
- **THEN** validate() refuses it, and the job's record says what was refused

### Requirement: A model may do the whole job itself
A harness's `output` MAY return a finished page: the page as it should be, what it erased, and pictures it made.
The host SHALL check it with `validate()` and commit what passes, as for any job, and a harness or its model
SHALL never write the mirror or the cloud. Abilities the harness's `declare()` says its model provides (its own
pictures, its own web search) SHALL count as met for the kinds that need them.

#### Scenario: A model with its own pictures
- **WHEN** a lineup has no image model and its text harness declares that its model makes pictures
- **THEN** the picture kinds are on for that lineup, with the reason "the model does it itself"
