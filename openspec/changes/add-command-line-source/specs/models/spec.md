## ADDED Requirements

### Requirement: A text slot can be served by a command-line program on this computer
The text slot SHALL accept a third source, the command line: its location the WHOLE command as the user types it (a
program's name or path, then the user's own arguments), its API family `cli`. A command-line slot SHALL have no model
field. PaperDaemon SHALL run the command EXACTLY as typed, with no shell between, once for each model call, and SHALL
ADD NOTHING to it: no argument, no setting, no environment. Nothing in PaperDaemon SHALL be particular to one program:
no adapter, harness, setting, label or string says how any program is run (the maintainer, 11-15: "THERE SHOULD BE NO
CLAUDE SPECIFIC HARNESS"). The program SHALL be spoken to the plainest way: the system text and the conversation on
its input as plain text; each picture saved as a file in the run's own folder (the program's working folder) and
named in the words where it is; what it prints taken as the answer, and with tools the JSON object in it read as the
calls. Whatever else the program needs (printing an answer and stopping, which model, how much effort, which of its
own tools it may use) SHALL be the command's to say. PaperDaemon SHALL NOT read, store or send a program's sign-in,
and SHALL NOT change or bundle a program; the help SHALL say the program must be signed in on this computer before the
lineup runs. Every file a request needs SHALL be made in a folder of its own and removed after the run. A program
that is not found SHALL be said so in plain words where the slot is tested and where a job fails. A slot saved with
the API family `claude-cli` SHALL be read as a command-line slot with the command `claude`, and a command-line slot
saved with a model beside its command SHALL keep its command as it is.

#### Scenario: A job on a lineup whose text source is a command
- **WHEN** a page tagged for a lineup whose text slot is the command `claude -p --model claude-opus-5-5 --effort
  medium --tools Read` is worked on
- **THEN** each turn of the job is one run of exactly that command, its input the system text and the conversation,
  the page's picture a file in its folder that the program opens, and the page is written as with any other model

#### Scenario: Nothing is added
- **WHEN** any command is run for a request
- **THEN** the program receives the user's arguments and no others

#### Scenario: The source is not an API key
- **WHEN** the user opens a lineup whose text model is a command
- **THEN** the form's Source reads "Command line", with the command and the harness under it, and no provider,
  address, key or model
