# Tasks

## 1. The first build (0.2.39), withdrawn by the maintainer's ruling

- [x] 1.1 An adapter for one program, a provider named after it under "API key", proven on real pages (11-10)
- [x] 1.2 The maintainer's ruling (11-10, on seeing the Lineup screen): "its not an api key, its a cli. This feels
      like you are overloading the api key and forcing claude specific tooling into the app"

## 2. The command-line source

- [x] 2.1 `models/cli.py`: a command found (as a file, on the PATH, in the places its harness names), run once a
      call in an empty folder with the request's files made there and removed after; arguments, input and output
      read from the harness's `cli` field; the plainest way for a program with no harness; nothing in it names a
      program
- [x] 2.2 The `cli` harness field (schema, loader, guide); the harness that speaks for a command; where a command's
      pages go (`cli.sends_to`)
- [x] 2.3 `cli` among the text slot's API families; a command checked as a command, not an address; a slot saved as
      `claude-cli` read as the command `claude`
- [x] 2.4 Shipped harnesses as data: "Claude Code (command line)" and "Claude Opus 5.5, medium effort" extending it
- [x] 2.5 The slot form: Source "Command line" with Command, Model and Harness; its words in the window's 19
      languages

## 3. Proof

- [x] 3.1 A real call through the real program by the general adapter (11-10: a forced tool call answered in 2.4 s)
- [x] 3.2 A real job in the False Mirror on the maintainer's lineup after the update, the slot read from his saved
      settings (11-10 on 0.2.42: a handwritten request, a labeled compass rose drawn in 21 s, three turns)
