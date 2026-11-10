# Proposal: add-command-line-source

## Why

The maintainer wants a lineup whose text model is reached through a command-line program installed on the computer
and signed in by its user (his case: Claude Opus 5.5 at medium effort through the `claude` program), with no API key
of PaperDaemon's.

The first build (0.2.39) shipped it as a provider named after that one program, under the source "API key", with an
adapter that knew the program's arguments and output. The maintainer's ruling on seeing it: it is not an API key, it
is a command line, and tooling shaped after one vendor's program does not belong in the app. This change is rebuilt
to that ruling.

## What Changes

- A third source for the text slot, beside "API key" and "Host locally": **Command line**. The slot's location is a
  command as typed (a program's name or path, with any arguments of the user's own); the API family is `cli`.
  PaperDaemon runs the command once for each turn of a job, hands it the request and reads what it prints.
- The adapter knows no program. How a program is spoken to is data, the `cli` field of a text harness: its usual
  name and where it is installed, the arguments a request adds, what goes on its input, where its answer is in what
  it prints, how to ask whether it is ready, where it sends a page, and the names it takes for its models. A program
  with no such harness is spoken to the plainest way: the system text and the conversation on its input, its answer
  what it prints.
- The harness that speaks for a command is the slot's own when that harness has a `cli` field, else the harness
  whose `cli.program` is the command's program.
- PaperDaemon never reads, stores or sends a program's sign-in, and changes and bundles nothing of it: the program
  runs as installed, signed in by whoever signed it in.
- The host's tools reach the model as one JSON schema for a structured answer. A program that checks an answer
  against a schema is handed it; for any other the schema's shape is said in the system text and the JSON object in
  what the program prints is read. A schema too long for a command line is sent with unchecked arguments, each
  tool's own schema in the system text.
- An argument may take any field of the request the harness tuned (`{request.output_config.effort}`): an effort is
  the harness's to set in its `request`, as for a server.
- Two shipped harnesses carry the maintainer's case as data: "Claude Code (command line)", the `cli` field for the
  command `claude`, and "Claude Opus 5.5, medium effort", which extends it and serves that model on the command line
  and on the API alike.
- A slot saved by 0.2.39 to 0.2.41 (API family `claude-cli`) is read as a command-line slot with the command
  `claude`.

## Impact

- Affected specs: models/slots (the sources of a text slot; the command-line source and the harness's `cli`
  field).
- Code: `paperdaemon/models/cli.py` (new; `models/claude_cli.py` removed), `paperdaemon/models/adapters.py`,
  `paperdaemon/models/slots.py`, `paperdaemon/settings.py`, `paperdaemon/harnesses/__init__.py`,
  `paperdaemon/harnesses/schema.py`, `paperdaemon/harnesses/shipped/claude-code.json` (new),
  `paperdaemon/harnesses/shipped/claude-opus-5.5.json`, `paperdaemon/harnesses/GUIDE-llm.md`,
  `paperdaemon/ui/slots.js`, `paperdaemon/ui/setup.js`, the window's strings.
- Where a command-line slot's pages go is what its harness says (`cli.sends_to`), for the off-machine notice.
