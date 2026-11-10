## ADDED Requirements

### Requirement: A text slot can be served by a command-line program on this computer
The text slot SHALL accept a third source, the command line: its location the WHOLE command as the user types it (a
program's name or path, then the user's own arguments, which model and how much effort among them), its API family
`cli`. A command-line slot SHALL have no model field: how a model is named is the program's own syntax, and the
command says it. PaperDaemon SHALL start the program itself, with no shell between, once for each model call, hand it
the request and read what it prints. What PaperDaemon adds to the command SHALL be only what carries a request in and
its answer out; it SHALL NOT add a model or an effort. Nothing in the application SHALL be particular
to one program: no adapter, setting, label or string names a vendor's program. What is particular to a program SHALL
be data in a text harness's `cli` field: the program's usual name and the places it is installed, the arguments a
request adds (with placeholders for the system text, the conversation, the tools' schema, a picture's
file and any field of the request the harness tuned; a group of arguments left out whole when a placeholder in it has
nothing to give, or when it begins with an argument the user's own command already gives), what goes on the program's
input, where the answer, an error and the token counts are in what it
prints, a command that says whether the program is ready and what to tell the user when it is not, the host it sends
a page to, and the argument after which a command names its model (so that the model's harness can be guessed from the
command; nothing is added for it). A harness that only holds what others share (a program's data) SHALL be able to
say it is not offered, and SHALL then not be listed where a harness is picked. The harness that speaks for a command SHALL be the slot's harness
when it has a `cli` field, else the harness whose `cli.program` is the command's program; a program with neither
SHALL be given the system text and the conversation on its input and its printed text taken as the answer.
PaperDaemon SHALL NOT read, store or send a program's sign-in, and SHALL NOT change or bundle a program. The host's
tools SHALL reach the model as one schema for a structured answer and the reply SHALL come back in the shape every
adapter returns. Every file a request needs SHALL be made in a folder of its own and removed after the run. The
off-machine notice SHALL name the host the harness says the program sends to, and none when it says none. A program
that is not found, or not ready, SHALL be said so in plain words where the slot is tested and where a job fails. A
slot saved with the API family `claude-cli` SHALL be read as a command-line slot with the command `claude`, and a
command-line slot saved with a model beside its command SHALL be read as the command naming that model itself.

#### Scenario: A job on a lineup whose text source is a command
- **WHEN** a page tagged for a lineup whose text slot is the command `claude --model claude-opus-5-5 --effort medium`
  is worked on
- **THEN** each turn of the job is one run of the program with the user's arguments as typed and, after them, the
  arguments the program's `cli` data gives for a request, and the page is written as with any other text model

#### Scenario: A program nobody wrote a harness for
- **WHEN** the command is a program no harness's `cli.program` names
- **THEN** the system text and the conversation go on its input, what it prints is the answer, and a tool call is
  read from the JSON object in what it prints

#### Scenario: The program is not ready
- **WHEN** the program is installed and its harness's readiness check says nobody is signed in
- **THEN** the slot's test and the job's note say what the harness says to do, and nothing is asked of the user
  inside PaperDaemon

#### Scenario: An argument typed in the command
- **WHEN** the command gives an argument that a group of the program's `cli` data begins with
- **THEN** the program is run with the argument the user typed, and the data's group is left out

#### Scenario: The source is not an API key
- **WHEN** the user opens a lineup whose text model is a command
- **THEN** the form's Source reads "Command line", with the command and the harness under it, and no provider,
  address, key or model

#### Scenario: A slot saved with a model beside its command
- **WHEN** settings saved by 0.2.42 to 0.2.47 hold the command `claude` and the model `claude-opus-5-5`
- **THEN** the slot is read as the command `claude --model claude-opus-5-5` with no model beside it

#### Scenario: One harness a model
- **WHEN** the user opens the Harness box of a command-line slot
- **THEN** it offers one harness for each model PaperDaemon is tuned for and Lean Default, and not the program's data
