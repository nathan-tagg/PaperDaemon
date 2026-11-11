# Proposal: remove-automatic-harness

## Why

A slot's harness could be left "Automatic (from the model's name)": PaperDaemon then matched the model's name, the
model the server reported and the model file in the start script against patterns in the harness files, and ran the
slot on whichever harness matched. The maintainer's ruling (11-10): "there should be no 'Automatic (from the
model's name)' default text - and that should not be a thing AT ALL. There should be ZERO inference from
paperdaemons perspective on what model it should use." With it: the base harnesses are named alike ("change the
'built in' to 'Default', so there is consistency"), and three harnesses that were the same thing under three model
names are one ("lets just condense the harnesses into the lean default").

## What Changes

- **BREAKING** A slot's harness is the one its user picked, the default of its kind until they pick another. The
  Harness box is a list that always holds a harness; "Automatic" is gone from it, from the settings and from the
  engine. Nothing matches a model's name, a server's report or a start script against anything.
- A slot saved as automatic by an earlier version is given, once, as its settings are read, the harness that
  version ran it on; from then on it is the slot's own pick. `patterns` and `refuse` in a harness file are read for
  that only.
- The base harnesses are named "Default". "Lean Default (stronger models only)" stays. The harnesses "Claude Opus
  5.5", "Claude Sonnet 5.5" and "Claude Haiku 5.5" are removed; a slot that named one names Lean Default.
- Nothing reads a model out of a command-line slot's command.
- The harnesses "llama.cpp - Qwen 3.6 27B" and "llama.cpp - Qwen 3.8 27B" are removed as well (0.2.53, "I say fold
  them in, but in their header state that they were designed for qwen 3 models running in llama.cpp"): they set
  nothing the default does not. Default's own header says what it was designed for; a slot, or a user's harness, that
  named one of them names Default.
- Each harness's header (`notes`) is its description, and the Lineup screen shows the picked harness's in a block
  under the Harness box ("the header block should be in code on the harness, and should be pulled into the lineup
  giving a description of what each harness is capable of - as well as warnings that using models without those
  capabilities will result in issues, and using a heavier harness on a stronger model will result in more token
  usage").

## Impact

- Affected specs: models/harnesses
- Code: `paperdaemon/harnesses/__init__.py` (no guess; `was_automatic` for the one upgrade), `schema.py`, the
  shipped files, both guides; `paperdaemon/models/slots.py`, `cli.py`; `paperdaemon/settings.py` (a slot's default
  harness; the upgrade); `paperdaemon/ui/slots.js`, `setup.js`, the strings in every language
- Tests: `tests/test_harnesses.py`, `tests/test_cli_slot.py`, `tests/test_lean_harness.py`, `tests/test_settings.py`
