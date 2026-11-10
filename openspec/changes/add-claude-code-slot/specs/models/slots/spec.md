## ADDED Requirements

### Requirement: A text slot can be served by Claude Code on this computer
The text slot SHALL accept the API family `claude-cli`: the Claude Code program installed on this computer, started
as it is published, once a model call, in its own non-interactive mode. PaperDaemon SHALL NOT read, store or send
the program's sign-in, and SHALL NOT change or bundle the program: the program signs in by itself, as the user who
signed it in. Each run SHALL have none of the program's own tools, none of the user's settings files, hooks or MCP
servers, and SHALL keep no session; the system text SHALL be the host's own. The host's tools SHALL reach the model
as one schema for the program's structured output, and the reply SHALL come back in the shape every adapter returns.
The slot's model and effort SHALL be passed to the program; the effort SHALL come from the harness's request fields
(`output_config.effort`). The off-machine notice SHALL name Anthropic's API as where the slot's pages go. A program
that is not installed, or not signed in, SHALL be said so in plain words where the slot is tested and where a job
fails.

#### Scenario: A job on a lineup served by Claude Code
- **WHEN** a page tagged for a lineup whose text slot is `claude-cli` with the model `claude-opus-5-5` is worked on
- **THEN** each turn of the job is one run of the program with that model and the harness's effort, and the page is
  written as with any other text model

#### Scenario: Claude Code is not signed in
- **WHEN** the program is installed but nobody is signed in to it
- **THEN** the slot's test and the job's note say to run the program once and sign in, and nothing is asked of the
  user inside PaperDaemon

#### Scenario: Nothing of the user's own Claude Code setup reaches a job
- **WHEN** the user's Claude Code has hooks, connected services and project instructions of its own
- **THEN** a job's run of the program uses none of them
