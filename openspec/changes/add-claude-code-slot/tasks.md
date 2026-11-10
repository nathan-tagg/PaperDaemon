# Tasks

## 1. The adapter

- [x] 1.1 `models/claude_cli.py`: the program found, run bare (no tools, settings, MCP servers or session), the system
      text from a file removed after, the conversation as blocks on its input, pictures as pictures
- [x] 1.2 The host's tools as one schema (`--json-schema`), loose when too long for a command line; the reply parsed
      into the neutral shape; the program's own error said as it said it; not installed and not signed in said plainly
- [x] 1.3 `claude-cli` among the text slot's API families; the adapter picked for the slot

## 2. The harness and the window

- [x] 2.1 The shipped harness "Claude Opus 5.5, medium effort" (`output_config.effort` in its request)
- [x] 2.2 "Claude Code" among the slot form's hosted providers, without a key field

## 3. Proof

- [x] 3.1 Real calls through the program: a reply, a forced tool call, a picture read, a second turn, the host's own
      23 tools (11-10: 2 to 4 s each on Claude Opus 5.5 at medium effort)
- [x] 3.2 A real job in the False Mirror on a lineup served by Claude Code, in the maintainer's running app (11-10 on
      0.2.39, lineup "Opus 5.5": a typed question answered in 6 s; a handwritten request read and a labeled sketch
      drawn in 23 s, three turns)
