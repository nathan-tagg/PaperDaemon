# Proposal: add-claude-code-slot

## Why

The maintainer wants a lineup whose text model is Claude Opus 5.5 at medium effort, reached through Claude Code, the
command-line program installed on the computer and signed in by its user, with no API key of PaperDaemon's.

## What Changes

- A third API family for the text slot, `claude-cli`: PaperDaemon starts the Claude Code program as published
  (`claude -p`), hands it one request and reads what it prints. The program runs with none of its own tools, none of
  the user's settings, hooks or MCP servers, and keeps no session; the system text is the host's own.
- PaperDaemon never reads, stores or sends the program's sign-in. The program signs in by itself, as the person who
  signed it in; nothing of it is changed or bundled, and the use is that person's under their own agreement with
  Anthropic (Anthropic's terms for running Claude Code in a product: the program unmodified, each user signed in
  themselves, no usage paid for or passed on by the product).
- The host's tools reach the model as one JSON schema for the program's structured output, each call checked against
  its tool's own schema; a tool list too long for a command line is sent with unchecked arguments and its schemas in
  the system text.
- The effort is the harness's to set, in its `request`, as `output_config.effort`, the field the Messages API itself
  takes: one shipped harness, "Claude Opus 5.5, medium effort", serves a slot on Claude Code and a slot on the API.
- The window's slot form offers "Claude Code" among the hosted providers, with no key field.

## Impact

- Affected specs: models/slots (the API families; a requirement for the Claude Code slot).
- Code: `paperdaemon/models/claude_cli.py` (new), `paperdaemon/models/adapters.py`, `paperdaemon/settings.py`,
  `paperdaemon/harnesses/shipped/claude-opus-5.5.json` (new), `paperdaemon/ui/slots.js`.
- The slot's pages go to Anthropic, as the off-machine notice says for any hosted slot.
